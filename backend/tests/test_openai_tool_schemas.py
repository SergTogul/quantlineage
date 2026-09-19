"""Unit tests for strict OpenAI function tool schema conversion (T03)."""

from __future__ import annotations

import copy
import json

import pytest

from app.ai.tool_schemas import (
    StrictToolSchemaError,
    normalize_strict_json_schema,
    openai_function_tool,
    openai_function_tools,
)
from app.risk.query import TOOL_CONTRACTS, RiskToolName, tool_json_schemas


def _collect_object_schemas(node: object, collected: list[dict[str, object]]) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            collected.append(node)
        for value in node.values():
            _collect_object_schemas(value, collected)
    elif isinstance(node, list):
        for item in node:
            _collect_object_schemas(item, collected)


def test_every_risk_tool_name_emitted_once() -> None:
    tools = openai_function_tools()
    names = [tool["name"] for tool in tools]

    assert len(tools) == len(RiskToolName)
    assert len(names) == len(set(names))
    assert set(names) == {name.value for name in RiskToolName}


def test_tool_names_and_descriptions_are_stable() -> None:
    for name in RiskToolName:
        contract = TOOL_CONTRACTS[name]
        tool = openai_function_tool(name)

        assert tool["name"] == contract.name.value
        assert tool["description"] == contract.description


def test_every_tool_is_strict_with_closed_object_schemas() -> None:
    for tool in openai_function_tools():
        assert tool["type"] == "function"
        assert tool["strict"] is True

        objects: list[dict[str, object]] = []
        _collect_object_schemas(tool["parameters"], objects)
        assert objects, f"{tool['name']} parameters must include an object schema"
        for obj in objects:
            assert obj.get("type") == "object"
            assert obj.get("additionalProperties") is False
            properties = obj.get("properties", {})
            assert obj.get("required") == list(properties)


def test_optional_nullable_fields_are_explicit() -> None:
    key_rate = openai_function_tool(RiskToolName.GET_KEY_RATE_DV01)
    tenor = key_rate["parameters"]["properties"]["tenor"]
    assert "tenor" in key_rate["parameters"]["required"]
    assert tenor["anyOf"] == [
        {"enum": ["2Y", "5Y", "10Y"], "type": "string"},
        {"type": "null"},
    ]
    assert "default" not in tenor

    portfolio_risk = openai_function_tool(RiskToolName.RUN_PORTFOLIO_RISK)
    snapshot = portfolio_risk["parameters"]["properties"]["market_snapshot_id"]
    assert "market_snapshot_id" in portfolio_risk["parameters"]["required"]
    assert snapshot["anyOf"] == [{"maxLength": 4096, "type": "string"}, {"type": "null"}]
    assert "default" not in snapshot


def test_defaulted_fields_become_required_without_defaults() -> None:
    compare = openai_function_tool(RiskToolName.COMPARE_RISK_RUNS)
    metric = compare["parameters"]["properties"]["metric"]
    assert "metric" in compare["parameters"]["required"]
    assert metric["enum"] == [
        "var_99",
        "var_95",
        "expected_shortfall_99",
        "dv01",
        "vega",
        "stress",
    ]
    assert metric["type"] == "string"
    assert "default" not in metric

    stress = openai_function_tool(RiskToolName.RUN_STRESS)
    scenario = stress["parameters"]["properties"]["scenario_id"]
    assert "scenario_id" in stress["parameters"]["required"]
    assert scenario["enum"] == [
        "eq_down_10",
        "rates_up_100",
        "vol_up_25",
        "eq_down_vol_up",
        "combined_crisis",
    ]
    assert "default" not in scenario


def test_conversion_does_not_mutate_contracts_or_source_schemas() -> None:
    contracts_before = {
        name: contract.model_dump(mode="json") for name, contract in TOOL_CONTRACTS.items()
    }
    schemas_before = copy.deepcopy(tool_json_schemas())

    openai_function_tools()

    contracts_after = {
        name: contract.model_dump(mode="json") for name, contract in TOOL_CONTRACTS.items()
    }
    schemas_after = tool_json_schemas()

    assert contracts_before == contracts_after
    assert schemas_before == schemas_after


def _collect_dict_keys(node: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(node, dict):
        keys.update(node)
        for value in node.values():
            keys.update(_collect_dict_keys(value))
    elif isinstance(node, list):
        for item in node:
            keys.update(_collect_dict_keys(item))
    return keys


def test_tools_do_not_expose_internal_fields_or_credentials() -> None:
    forbidden_keys = {
        "service_method",
        "http_path",
        "numeric_source",
        "required_inputs",
        "returns",
        "provenance_fields",
        "credentials",
        "api_key",
        "secret",
    }
    for tool in openai_function_tools():
        assert set(tool) == {"type", "name", "description", "parameters", "strict"}
        assert forbidden_keys.isdisjoint(_collect_dict_keys(tool))
        assert "OPENAI_API_KEY" not in tool["description"]
        assert "sk-live" not in json.dumps(tool)


@pytest.mark.parametrize(
    ("schema", "message"),
    [
        ({"type": "string"}, "root schema type must be object"),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {"value": {"$ref": "#/$defs/Value"}},
            },
            "unsupported schema construct: $ref",
        ),
        (
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "value": {
                        "anyOf": [{"type": "string"}, {"type": "number"}],
                    }
                },
            },
            "unsupported schema construct: anyOf",
        ),
        (
            {
                "type": "object",
                "additionalProperties": True,
                "properties": {},
            },
            "object schemas must set additionalProperties to false",
        ),
    ],
)
def test_unsupported_schemas_fail_closed_with_tool_name(
    schema: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(StrictToolSchemaError) as exc_info:
        normalize_strict_json_schema(schema, "get_var_es")

    assert exc_info.value.tool_name == "get_var_es"
    assert message in str(exc_info.value)
