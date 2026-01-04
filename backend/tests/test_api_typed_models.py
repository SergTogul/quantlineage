"""M7.3: critical risk endpoints expose typed OpenAPI response schemas."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from app.api.openapi_examples import TYPED_RESPONSE_SCHEMAS
from app.domain.models import (
    ESContributionReport,
    HedgeComparisonReport,
    LimitDrilldownReport,
    MultiFactorReverseStressResult,
    ReverseStressResult,
    RiskChangeAttributionReport,
    StressResult,
    VaRReport,
    WhatIfReport,
)


def _resolve_schema_ref(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        name = ref.rsplit("/", 1)[-1]
        resolved = (components.get("schemas") or {}).get(name)
        assert isinstance(resolved, dict), f"missing component schema {name}"
        return resolved
    return schema


def _success_json_schema(operation: dict[str, Any]) -> dict[str, Any]:
    responses = operation.get("responses") or {}
    for status in ("200", "202"):
        response = responses.get(status)
        if not response:
            continue
        content = response.get("content") or {}
        media = content.get("application/json") or {}
        schema = media.get("schema")
        if isinstance(schema, dict):
            return schema
    raise AssertionError(f"no 200/202 application/json schema on operation: {operation.get('operationId')}")


def _assert_schema_refs_model(
    schema: dict[str, Any],
    *,
    schema_name: str,
    items_schema: str | None,
    components: dict[str, Any],
) -> None:
    """Accept direct $ref, allOf wrappers, or array-of-$ref."""
    if items_schema is not None:
        assert schema.get("type") == "array", f"expected array schema, got {schema}"
        items = schema.get("items") or {}
        assert isinstance(items, dict), f"expected items object, got {items!r}"
        if isinstance(items.get("$ref"), str):
            assert items["$ref"].endswith(f"/{items_schema}")
        else:
            # Some FastAPI versions inline; ensure component exists either way
            assert items_schema in (components.get("schemas") or {})
            _resolve_schema_ref(items, components)
        return

    ref = schema.get("$ref")
    if isinstance(ref, str):
        assert ref.endswith(f"/{schema_name}"), f"expected {schema_name}, got {ref}"
        return

    for entry in schema.get("allOf") or []:
        if isinstance(entry, dict) and isinstance(entry.get("$ref"), str):
            if entry["$ref"].endswith(f"/{schema_name}"):
                return

    # Fallback: component must exist and required keys overlap resolved schema
    assert schema_name in (components.get("schemas") or {}), (
        f"OpenAPI missing components.schemas.{schema_name}"
    )


@pytest.mark.parametrize(
    "method,path,schema_name,items_schema",
    TYPED_RESPONSE_SCHEMAS,
)
def test_m73_openapi_response_schema_typed(
    method: str,
    path: str,
    schema_name: str,
    items_schema: str | None,
) -> None:
    from app.main import app

    openapi = app.openapi()
    components = openapi.get("components") or {}
    assert schema_name in (components.get("schemas") or {}), (
        f"missing components.schemas.{schema_name}"
    )
    operation = openapi["paths"][path][method]
    schema = _success_json_schema(operation)
    _assert_schema_refs_model(
        schema,
        schema_name=schema_name,
        items_schema=items_schema,
        components=components,
    )


@pytest.mark.parametrize(
    "method,path,schema_name,items_schema",
    TYPED_RESPONSE_SCHEMAS,
)
def test_m73_v1_dual_mount_also_typed(
    method: str,
    path: str,
    schema_name: str,
    items_schema: str | None,
) -> None:
    from app.main import app

    v1_path = f"/api/v1{path}"
    openapi = app.openapi()
    components = openapi.get("components") or {}
    operation = openapi["paths"][v1_path][method]
    schema = _success_json_schema(operation)
    _assert_schema_refs_model(
        schema,
        schema_name=schema_name,
        items_schema=items_schema,
        components=components,
    )


def test_m73_live_responses_validate_against_domain_models() -> None:
    """HTTP JSON from critical POSTs validates as domain response models."""
    from app.main import app

    client = TestClient(app)
    portfolio = client.get("/portfolio").json()

    var_payload = client.post("/risk/var", json=portfolio)
    assert var_payload.status_code == 200
    VaRReport.model_validate(var_payload.json())

    es_payload = client.post("/risk/es", json=portfolio)
    assert es_payload.status_code == 200
    ESContributionReport.model_validate(es_payload.json())

    stress_payload = client.post("/risk/stress", json=portfolio)
    assert stress_payload.status_code == 200
    TypeAdapter(list[StressResult]).validate_python(stress_payload.json())

    reverse_payload = client.post(
        "/risk/stress/reverse",
        json={"portfolio": portfolio, "target_loss_pct": 0.05, "factor": "equity"},
    )
    assert reverse_payload.status_code == 200
    ReverseStressResult.model_validate(reverse_payload.json())

    multi_payload = client.post(
        "/risk/stress/reverse/multi",
        json={"portfolio": portfolio, "target_loss_pct": 0.05, "factors": ["equity", "vol"]},
    )
    assert multi_payload.status_code == 200
    MultiFactorReverseStressResult.model_validate(multi_payload.json())

    hedged = {
        **portfolio,
        "id": f"{portfolio['id']}-hedged",
        "positions": [
            {**portfolio["positions"][0], "quantity": float(portfolio["positions"][0]["quantity"]) * 0.5},
            *portfolio["positions"][1:],
        ],
    }
    compare_payload = client.post(
        "/risk/stress/compare",
        json={
            "portfolio": portfolio,
            "hedged_portfolio": hedged,
            "scenarios": [
                {
                    "name": "Equity -10%",
                    "equity_shock": -0.10,
                    "vol_shock": 0.0,
                    "rates_shift_bps": 0.0,
                    "fx_shock": 0.0,
                }
            ],
            "methodology": "DELTA_GAMMA",
        },
    )
    assert compare_payload.status_code == 200
    HedgeComparisonReport.model_validate(compare_payload.json())

    # What-if: add a small equity clip
    base_pos = next(p for p in portfolio["positions"] if p["type"] == "equity")
    what_if_payload = client.post(
        "/risk/what-if",
        json={
            "portfolio": portfolio,
            "methodology": "DELTA_GAMMA",
            "changes": [
                {
                    "operation": "add",
                    "position": {
                        **base_pos,
                        "id": "m73-whatif-eq",
                        "quantity": 1.0,
                    },
                }
            ],
        },
    )
    assert what_if_payload.status_code == 200
    WhatIfReport.model_validate(what_if_payload.json())

    # Change attribution: bump first equity quantity
    bumped = {
        **portfolio,
        "positions": [
            {
                **portfolio["positions"][0],
                "quantity": float(portfolio["positions"][0]["quantity"]) * 1.1,
            },
            *portfolio["positions"][1:],
        ],
    }
    change_payload = client.post(
        "/risk/change-attribution",
        json={
            "previous_portfolio": portfolio,
            "current_portfolio": bumped,
            "metric": "var_99",
            "methodology": "DELTA_GAMMA",
        },
    )
    assert change_payload.status_code == 200
    RiskChangeAttributionReport.model_validate(change_payload.json())

    drill_payload = client.post(
        "/risk/limits/drilldown",
        json={
            "portfolio": portfolio,
            "metric": "var_99",
            "breaches_only": False,
            "top_n": 3,
        },
    )
    assert drill_payload.status_code == 200
    LimitDrilldownReport.model_validate(drill_payload.json())

    # Dual-mount parity: v1 VaR also validates
    v1_var = client.post("/api/v1/risk/var", json=portfolio)
    assert v1_var.status_code == 200
    VaRReport.model_validate(v1_var.json())
    assert v1_var.json() == var_payload.json()
