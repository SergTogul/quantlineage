"""R0.11.5 / RF-014: shared-deployment token gate.

Local demo (unset shared flag, loopback bind, default Compose) stays
unauthenticated. A shared / non-loopback profile fails closed without
``RISKFORGE_API_TOKEN`` and requires ``Authorization: Bearer`` on API routes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_mod
from app.main import app

COMPOSE_PATH = Path(__file__).resolve().parents[2] / "docker-compose.yml"
SHARED_TOKEN = "r0-11-5-shared-token"


def _assert_error_shape(body: dict[str, Any]) -> None:
    assert set(body.keys()) == {"code", "message", "details"}
    assert isinstance(body["code"], str) and body["code"]
    assert isinstance(body["message"], str) and body["message"]
    assert body["details"] is None or isinstance(body["details"], (dict, list))


def _clear_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(auth_mod.ENV_SHARED_DEPLOYMENT, raising=False)
    monkeypatch.delenv(auth_mod.ENV_API_TOKEN, raising=False)
    monkeypatch.delenv(auth_mod.ENV_API_TOKENS, raising=False)
    monkeypatch.delenv(auth_mod.ENV_BIND, raising=False)


def _enable_shared(monkeypatch: pytest.MonkeyPatch, *, token: str | None) -> None:
    monkeypatch.setenv(auth_mod.ENV_SHARED_DEPLOYMENT, "1")
    monkeypatch.delenv(auth_mod.ENV_BIND, raising=False)
    if token is None:
        monkeypatch.delenv(auth_mod.ENV_API_TOKEN, raising=False)
    else:
        monkeypatch.setenv(auth_mod.ENV_API_TOKEN, token)


def test_local_default_has_no_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_gate(monkeypatch)
    assert auth_mod.is_shared_deployment() is False
    auth_mod.require_shared_auth_configured()
    with TestClient(app) as client:
        health = client.get("/health")
        portfolio = client.get("/portfolio")
        api_portfolio = client.get("/api/v1/portfolio")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert portfolio.status_code == 200
    assert api_portfolio.status_code == 200


def test_loopback_bind_stays_unauthenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_gate(monkeypatch)
    for bind in ("127.0.0.1", "localhost", "::1"):
        monkeypatch.setenv(auth_mod.ENV_BIND, bind)
        assert auth_mod.is_shared_deployment() is False
        auth_mod.require_shared_auth_configured()
        with TestClient(app) as client:
            response = client.get("/api/v1/portfolio")
        assert response.status_code == 200, bind


def test_shared_profile_without_token_refuses_to_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_shared(monkeypatch, token=None)
    assert auth_mod.is_shared_deployment() is True
    with pytest.raises(RuntimeError, match="RISKFORGE_API_TOKEN"):
        auth_mod.require_shared_auth_configured()
    with pytest.raises(RuntimeError, match="RISKFORGE_API_TOKEN"), TestClient(app):
        pass


def test_non_loopback_bind_without_token_refuses_to_boot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_gate(monkeypatch)
    monkeypatch.setenv(auth_mod.ENV_BIND, "0.0.0.0")
    assert auth_mod.is_shared_deployment() is True
    with pytest.raises(RuntimeError, match="RISKFORGE_API_TOKEN"):
        auth_mod.require_shared_auth_configured()


def test_shared_without_token_refuses_api_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail closed on the request path even if lifespan is skipped."""
    _enable_shared(monkeypatch, token=None)
    # Bare TestClient does not enter lifespan (this Starlette build has no lifespan=).
    client = TestClient(app)
    response = client.get("/api/v1/portfolio")
    assert response.status_code == 401
    body = response.json()
    _assert_error_shape(body)
    assert body["code"] == "unauthorized"


def test_shared_with_token_rejects_unauthenticated_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_shared(monkeypatch, token=SHARED_TOKEN)
    auth_mod.require_shared_auth_configured()
    with TestClient(app) as client:
        missing = client.get("/api/v1/portfolio")
        wrong = client.get(
            "/api/v1/portfolio",
            headers={"Authorization": "Bearer wrong-token"},
        )
        legacy = client.get("/portfolio")
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert legacy.status_code == 401
    for response in (missing, wrong, legacy):
        body = response.json()
        _assert_error_shape(body)
        assert body["code"] == "unauthorized"
        assert response.headers.get("www-authenticate", "").lower().startswith("bearer")


def test_shared_with_token_accepts_authorization_bearer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_shared(monkeypatch, token=SHARED_TOKEN)
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/portfolio",
            headers={"Authorization": f"Bearer {SHARED_TOKEN}"},
        )
        legacy = client.get(
            "/portfolio",
            headers={"Authorization": f"Bearer {SHARED_TOKEN}"},
        )
    assert response.status_code == 200
    assert legacy.status_code == 200
    assert response.json()["id"]


def test_shared_health_and_docs_stay_open(monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_shared(monkeypatch, token=SHARED_TOKEN)
    with TestClient(app) as client:
        health = client.get("/health")
        api_health = client.get("/api/v1/health")
        docs = client.get("/docs")
        openapi = client.get("/openapi.json")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert api_health.status_code == 200
    assert docs.status_code == 200
    assert openapi.status_code == 200


def test_default_compose_stays_unauthenticated_local_demo() -> None:
    """Default Compose must not assign the shared-profile env vars."""
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    assert "RISKFORGE_SHARED_DEPLOYMENT:" not in text
    assert "RISKFORGE_API_TOKEN:" not in text
    assert "RISKFORGE_BIND:" not in text


def test_overlapping_token_keeps_tokens_map_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Compose requires TOKEN; overlapping secret must not remap Alice to shared."""
    _clear_gate(monkeypatch)
    monkeypatch.setenv(auth_mod.ENV_SHARED_DEPLOYMENT, "1")
    monkeypatch.setenv(auth_mod.ENV_API_TOKENS, f"alice:{SHARED_TOKEN}")
    monkeypatch.setenv(auth_mod.ENV_API_TOKEN, SHARED_TOKEN)
    monkeypatch.setenv(auth_mod.ENV_API_PRINCIPAL, "shared")
    principal = auth_mod.principal_for_bearer(f"Bearer {SHARED_TOKEN}")
    assert principal == "alice"
    assert principal != "shared"


def test_tokens_only_boots_without_single_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_gate(monkeypatch)
    monkeypatch.setenv(auth_mod.ENV_SHARED_DEPLOYMENT, "1")
    monkeypatch.setenv(auth_mod.ENV_API_TOKENS, f"alice:{SHARED_TOKEN}")
    auth_mod.require_shared_auth_configured()
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/portfolio",
            headers={"Authorization": f"Bearer {SHARED_TOKEN}"},
        )
    assert response.status_code == 200
