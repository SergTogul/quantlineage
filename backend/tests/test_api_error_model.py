"""M7.5: API errors use ``{code, message, details}`` on legacy and /api/v1 paths."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.errors import (
    ErrorBody,
    body_from_http_exception,
    body_from_validation_error,
    body_internal_error,
    code_for_status,
    error_payload,
    register_exception_handlers,
)
from app.domain.models import EquityPosition, Portfolio


def _assert_error_shape(body: dict[str, Any]) -> None:
    assert set(body.keys()) == {"code", "message", "details"}
    assert isinstance(body["code"], str) and body["code"]
    assert isinstance(body["message"], str) and body["message"]
    assert body["details"] is None or isinstance(body["details"], (dict, list))


@pytest.fixture
def tiny_portfolio() -> Portfolio:
    return Portfolio(
        id="err-model-book",
        name="Error Model Book",
        positions=[
            EquityPosition(
                type="equity", id="eq-1", symbol="AAPL", quantity=10, price=100.0
            )
        ],
    )


def test_error_payload_helper_shape() -> None:
    payload = error_payload(code="bad_request", message="nope", details={"k": 1})
    _assert_error_shape(payload)
    assert payload == {"code": "bad_request", "message": "nope", "details": {"k": 1}}


def test_body_from_http_exception_string_detail() -> None:
    body = body_from_http_exception(
        HTTPException(status_code=404, detail="risk run not found: x")
    )
    assert body == ErrorBody(
        code="not_found",
        message="risk run not found: x",
        details=None,
    )


def test_body_from_http_exception_structured_detail() -> None:
    body = body_from_http_exception(
        HTTPException(
            status_code=400,
            detail={
                "code": "unsupported_run_type",
                "message": "unsupported run_type: foo",
                "details": {"run_type": "foo"},
            },
        )
    )
    assert body.code == "unsupported_run_type"
    assert body.message == "unsupported run_type: foo"
    assert body.details == {"run_type": "foo"}


def test_body_from_validation_error() -> None:
    try:
        ErrorBody.model_validate({"code": 1, "message": "x"})
    except ValidationError as exc:
        rve = RequestValidationError(exc.errors())
    else:
        pytest.fail("expected ValidationError")

    body = body_from_validation_error(rve)
    assert body.code == "validation_error"
    assert body.message == "Request validation failed"
    assert isinstance(body.details, dict)
    assert "errors" in body.details
    assert isinstance(body.details["errors"], list)


def test_body_internal_error_opaque() -> None:
    body = body_internal_error()
    assert body.code == "internal_error"
    assert "unexpected" in body.message.lower()
    assert body.details is None


def test_code_for_status_known_and_fallback() -> None:
    assert code_for_status(400) == "bad_request"
    assert code_for_status(422) == "validation_error"
    assert code_for_status(503) == "service_unavailable"
    assert code_for_status(418) == "http_418"


@pytest.fixture
def api_client():
    from app.main import app

    with TestClient(app) as client:
        yield client


def test_m75_404_shape_legacy_and_v1(api_client: TestClient) -> None:
    for path in ("/risk/runs/does-not-exist", "/api/v1/risk/runs/does-not-exist"):
        resp = api_client.get(path)
        assert resp.status_code == 404
        body = resp.json()
        _assert_error_shape(body)
        assert body["code"] == "not_found"
        assert "not found" in body["message"].lower()
        assert body["details"] is None


def test_m75_400_what_if_shape_legacy_and_v1(api_client: TestClient) -> None:
    portfolio = api_client.get("/portfolio").json()
    payload = {
        "portfolio": portfolio,
        "changes": [{"operation": "remove", "position_id": "does-not-exist"}],
    }
    for path in ("/risk/what-if", "/api/v1/risk/what-if"):
        resp = api_client.post(path, json=payload)
        assert resp.status_code == 400
        err = resp.json()
        _assert_error_shape(err)
        assert err["code"] == "bad_request"
        assert err["message"]
        assert err["details"] is None


def test_m75_422_validation_shape_legacy_and_v1(
    api_client: TestClient, tiny_portfolio: Portfolio
) -> None:
    payload = {
        "portfolio": tiny_portfolio.model_dump(mode="json"),
        "run_type": "",
    }
    for path in ("/risk/runs", "/api/v1/risk/runs"):
        resp = api_client.post(path, json=payload)
        assert resp.status_code == 422
        err = resp.json()
        _assert_error_shape(err)
        assert err["code"] == "validation_error"
        assert "validation" in err["message"].lower()
        assert isinstance(err["details"], dict)
        assert isinstance(err["details"]["errors"], list)
        assert err["details"]["errors"]


def test_m75_unsupported_run_type_400_message(
    api_client: TestClient, tiny_portfolio: Portfolio
) -> None:
    resp = api_client.post(
        "/risk/runs",
        json={
            "portfolio": tiny_portfolio.model_dump(mode="json"),
            "run_type": "not-a-real-type",
        },
    )
    assert resp.status_code == 400
    err = resp.json()
    _assert_error_shape(err)
    assert err["code"] == "bad_request"
    assert "unsupported run_type" in err["message"]


def test_m75_unhandled_500_shape() -> None:
    """Safe 500 probe on a minimal app with the same handlers (no prod route)."""
    probe = FastAPI()
    register_exception_handlers(probe)

    @probe.get("/__boom")
    def _boom() -> None:
        raise RuntimeError("intentional probe — must not leak")

    with TestClient(probe, raise_server_exceptions=False) as client:
        resp = client.get("/__boom")
    assert resp.status_code == 500
    err = resp.json()
    _assert_error_shape(err)
    assert err["code"] == "internal_error"
    assert "intentional" not in err["message"].lower()
    assert err["details"] is None


def test_m75_success_unchanged(api_client: TestClient) -> None:
    health = api_client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert "code" not in health.json()
