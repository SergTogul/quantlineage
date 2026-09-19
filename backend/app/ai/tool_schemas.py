"""Convert TOOL_CONTRACTS JSON schemas to strict OpenAI Responses API function tools."""

from __future__ import annotations

import copy
from typing import Any

from app.risk.query import TOOL_CONTRACTS, RiskToolName, tool_json_schemas

_UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {
        "$ref",
        "$defs",
        "definitions",
        "$anchor",
        "$dynamicAnchor",
        "oneOf",
        "allOf",
        "not",
        "if",
        "then",
        "else",
        "patternProperties",
        "unevaluatedProperties",
        "dependentSchemas",
        "dependentRequired",
        "prefixItems",
    }
)

_ALLOWED_PRIMITIVE_TYPES = frozenset({"string", "number", "integer", "boolean", "null"})

_METADATA_KEYS_TO_STRIP = frozenset({"title", "description", "default"})


class StrictToolSchemaError(ValueError):
    """Raised when a contract schema cannot be converted to OpenAI strict mode."""

    def __init__(self, tool_name: str, message: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"{tool_name}: {message}")


def openai_function_tools() -> list[dict[str, Any]]:
    """Return one strict OpenAI function tool per RiskToolName."""
    return [openai_function_tool(name) for name in RiskToolName]


def openai_function_tool(name: RiskToolName) -> dict[str, Any]:
    """Build a single strict OpenAI function tool from TOOL_CONTRACTS."""
    contract = TOOL_CONTRACTS[name]
    source_schema = tool_json_schemas()[contract.name.value]
    parameters = normalize_strict_json_schema(copy.deepcopy(source_schema), contract.name.value)
    return {
        "type": "function",
        "name": contract.name.value,
        "description": contract.description,
        "parameters": parameters,
        "strict": True,
    }


def normalize_strict_json_schema(schema: dict[str, Any], tool_name: str) -> dict[str, Any]:
    """Normalize a JSON Schema object for OpenAI strict function parameters."""
    _reject_unsupported_schema(schema, tool_name)
    if schema.get("type") != "object":
        raise StrictToolSchemaError(tool_name, "root schema type must be object")
    if schema.get("additionalProperties") is not False:
        raise StrictToolSchemaError(
            tool_name,
            "root schema additionalProperties must be false",
        )
    return _normalize_object_schema(schema, tool_name)


def _reject_unsupported_schema(node: Any, tool_name: str) -> None:
    if isinstance(node, dict):
        for key in node:
            if key in _UNSUPPORTED_SCHEMA_KEYS:
                raise StrictToolSchemaError(tool_name, f"unsupported schema construct: {key}")
            if key == "anyOf" and not _is_nullable_union(node[key]):
                raise StrictToolSchemaError(tool_name, "unsupported schema construct: anyOf")
            if key == "type" and isinstance(node[key], list) and not _is_nullable_type_list(
                node[key]
            ):
                raise StrictToolSchemaError(
                    tool_name,
                    f"unsupported schema construct: type {node[key]!r}",
                )
            if key == "additionalProperties" and node[key] is not False:
                raise StrictToolSchemaError(
                    tool_name,
                    "object schemas must set additionalProperties to false",
                )
        for value in node.values():
            _reject_unsupported_schema(value, tool_name)
    elif isinstance(node, list):
        for item in node:
            _reject_unsupported_schema(item, tool_name)


def _is_nullable_union(any_of: Any) -> bool:
    if not isinstance(any_of, list) or len(any_of) != 2:
        return False
    has_null = False
    has_value = False
    for item in any_of:
        if not isinstance(item, dict):
            return False
        if item == {"type": "null"}:
            has_null = True
            continue
        if "type" in item and item["type"] in _ALLOWED_PRIMITIVE_TYPES - {"null"}:
            if len(item) == 1 or _is_primitive_schema(item):
                has_value = True
                continue
        return False
    return has_null and has_value


def _is_primitive_schema(node: dict[str, Any]) -> bool:
    allowed = {"type", "enum", "format", "minLength", "maxLength", "minimum", "maximum"}
    return set(node) <= allowed


def _is_nullable_type_list(types: list[Any]) -> bool:
    if len(types) != 2 or "null" not in types:
        return False
    other = next(item for item in types if item != "null")
    return other in _ALLOWED_PRIMITIVE_TYPES - {"null"}


def _normalize_object_schema(schema: dict[str, Any], tool_name: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
    }
    properties = schema.get("properties") or {}
    if not isinstance(properties, dict):
        raise StrictToolSchemaError(tool_name, "properties must be an object")

    normalized_properties: dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        if not isinstance(prop_schema, dict):
            raise StrictToolSchemaError(tool_name, f"property {prop_name!r} must be an object")
        normalized_properties[prop_name] = _normalize_property_schema(
            prop_schema,
            tool_name,
            prop_name,
        )

    normalized["properties"] = normalized_properties
    normalized["required"] = list(normalized_properties)
    return normalized


def _normalize_property_schema(
    schema: dict[str, Any],
    tool_name: str,
    prop_name: str,
) -> dict[str, Any]:
    if schema.get("type") == "object" or "properties" in schema:
        nested = dict(schema)
        for key in _METADATA_KEYS_TO_STRIP:
            nested.pop(key, None)
        return _normalize_object_schema(nested, tool_name)

    if schema.get("type") == "array" or "items" in schema:
        raise StrictToolSchemaError(tool_name, f"unsupported property type for {prop_name!r}: array")

    normalized: dict[str, Any] = {}
    for key, value in schema.items():
        if key in _METADATA_KEYS_TO_STRIP:
            continue
        normalized[key] = value

    if "anyOf" in normalized:
        if not _is_nullable_union(normalized["anyOf"]):
            raise StrictToolSchemaError(
                tool_name,
                f"unsupported nullable schema for {prop_name!r}",
            )
        return normalized

    schema_type = normalized.get("type")
    if schema_type is None and "enum" in normalized:
        normalized["type"] = "string"
    elif isinstance(schema_type, list):
        if not _is_nullable_type_list(schema_type):
            raise StrictToolSchemaError(
                tool_name,
                f"unsupported property type for {prop_name!r}: {schema_type!r}",
            )
    elif schema_type not in _ALLOWED_PRIMITIVE_TYPES - {"null"}:
        raise StrictToolSchemaError(
            tool_name,
            f"unsupported property type for {prop_name!r}: {schema_type!r}",
        )

    return normalized
