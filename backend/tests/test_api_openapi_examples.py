"""M7.4: OpenAPI schema includes request/response (and error) examples."""

from __future__ import annotations

from typing import Any

import pytest

from app.api.openapi_examples import CRITICAL_OPENAPI_PATHS


def _media_has_examples(media: dict[str, Any] | None) -> bool:
    if not media:
        return False
    if media.get("example") is not None:
        return True
    examples = media.get("examples")
    return isinstance(examples, dict) and len(examples) > 0


def _schema_has_examples(schema: dict[str, Any] | None, components: dict[str, Any]) -> bool:
    """Walk a schema (or $ref) for json_schema examples / example."""
    if not schema:
        return False
    if schema.get("example") is not None:
        return True
    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        return True
    if isinstance(examples, dict) and examples:
        return True
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        name = ref.rsplit("/", 1)[-1]
        resolved = (components.get("schemas") or {}).get(name)
        return _schema_has_examples(resolved, components)
    return False


def _operation_has_documented_examples(
    operation: dict[str, Any],
    components: dict[str, Any],
) -> bool:
    """True if request body, any response, or response-model schema carries examples."""
    request_body = operation.get("requestBody") or {}
    for media in (request_body.get("content") or {}).values():
        if _media_has_examples(media):
            return True
        if _schema_has_examples(media.get("schema"), components):
            return True

    for response in (operation.get("responses") or {}).values():
        content = response.get("content") or {}
        for media in content.values():
            if _media_has_examples(media):
                return True
            if _schema_has_examples(media.get("schema"), components):
                return True
    return False


def _operation_error_examples_use_m75_shape(operation: dict[str, Any]) -> bool:
    """At least one 4xx response example uses ``{code,message,details}`` when present."""
    found_error_example = False
    for status, response in (operation.get("responses") or {}).items():
        if not str(status).startswith(("4", "5")):
            continue
        for media in (response.get("content") or {}).values():
            examples = media.get("examples") or {}
            for ex in examples.values():
                value = ex.get("value") if isinstance(ex, dict) else None
                if not isinstance(value, dict):
                    continue
                found_error_example = True
                assert "code" in value and "message" in value and "details" in value, (
                    f"error example missing M7.5 keys: {value!r}"
                )
            example = media.get("example")
            if isinstance(example, dict):
                found_error_example = True
                assert "code" in example and "message" in example and "details" in example
    return found_error_example


@pytest.mark.parametrize("method,path", CRITICAL_OPENAPI_PATHS)
def test_m74_critical_paths_have_openapi_examples(method: str, path: str) -> None:
    from app.main import app

    openapi = app.openapi()
    paths = openapi["paths"]
    assert path in paths, f"missing OpenAPI path {path}"
    operation = paths[path].get(method)
    assert operation is not None, f"missing {method.upper()} {path}"
    assert _operation_has_documented_examples(
        operation, openapi.get("components") or {}
    ), f"{method.upper()} {path} has no request/response OpenAPI examples"


@pytest.mark.parametrize("method,path", CRITICAL_OPENAPI_PATHS)
def test_m74_v1_dual_mount_also_has_examples(method: str, path: str) -> None:
    from app.main import app

    v1_path = f"/api/v1{path}"
    openapi = app.openapi()
    operation = openapi["paths"][v1_path][method]
    assert _operation_has_documented_examples(
        operation, openapi.get("components") or {}
    ), f"{method.upper()} {v1_path} missing examples"


def test_m74_error_examples_use_code_message_details() -> None:
    """Critical paths that document 4xx include M7.5 error shape examples."""
    from app.main import app

    openapi = app.openapi()
    paths_with_error_examples = 0
    for method, path in CRITICAL_OPENAPI_PATHS:
        operation = openapi["paths"][path][method]
        if _operation_error_examples_use_m75_shape(operation):
            paths_with_error_examples += 1
    # VaR/ES/stress may only document 422; what-if/limits/runs document 400/404.
    assert paths_with_error_examples >= 5, (
        f"expected several critical paths to document M7.5 error examples, "
        f"got {paths_with_error_examples}"
    )


def test_m74_var_request_and_response_examples_present() -> None:
    from app.main import app

    op = app.openapi()["paths"]["/risk/var"]["post"]
    req_examples = op["requestBody"]["content"]["application/json"]["examples"]
    assert "demo_book" in req_examples
    assert "portfolio_id" not in req_examples["demo_book"]["value"]  # body is Portfolio
    assert "id" in req_examples["demo_book"]["value"]

    resp_examples = op["responses"]["200"]["content"]["application/json"]["examples"]
    assert "illustrative" in resp_examples
    value = resp_examples["illustrative"]["value"]
    assert "methods" in value and "contributions" in value

    err = op["responses"]["422"]["content"]["application/json"]["examples"][
        "validation_error"
    ]["value"]
    assert err["code"] == "validation_error"
    assert err["message"]
    assert "details" in err


def test_m74_hedge_compare_documents_hedge_comparison_fields() -> None:
    from app.main import app

    op = app.openapi()["paths"]["/risk/stress/compare"]["post"]
    value = op["responses"]["200"]["content"]["application/json"]["examples"][
        "illustrative"
    ]["value"]
    for key in (
        "hedge_cost",
        "var_improvement",
        "es_improvement",
        "base_var_99",
        "hedged_var_99",
        "scenarios",
    ):
        assert key in value
