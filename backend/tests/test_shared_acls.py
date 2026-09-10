"""RF-014: shared-profile object ACLs (IDOR fail-closed).

Local demo stays unauthenticated. Shared profile maps Bearer tokens to
principals (not OIDC). One principal cannot read/update another principal's
stored portfolio or its risk runs (403). Seed/demo catalog stays readable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import auth as auth_mod
from app.main import app

ALICE_TOKEN = "rf014-alice-token"
BOB_TOKEN = "rf014-bob-token"
TOKEN_MAP = f"alice:{ALICE_TOKEN},bob:{BOB_TOKEN}"

_TINY = {
    "id": "alice-private-book",
    "name": "Alice Private Book",
    "positions": [
        {"type": "equity", "id": "eq-1", "symbol": "AAPL", "quantity": 10},
    ],
}


def _assert_error_shape(body: dict[str, Any]) -> None:
    assert set(body.keys()) == {"code", "message", "details"}
    assert isinstance(body["code"], str) and body["code"]
    assert isinstance(body["message"], str) and body["message"]
    assert body["details"] is None or isinstance(body["details"], (dict, list))


def _clear_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(auth_mod.ENV_SHARED_DEPLOYMENT, raising=False)
    monkeypatch.delenv(auth_mod.ENV_API_TOKEN, raising=False)
    monkeypatch.delenv("RISKFORGE_API_TOKENS", raising=False)
    monkeypatch.delenv(auth_mod.ENV_BIND, raising=False)
    monkeypatch.delenv("RISKFORGE_DATABASE_URL", raising=False)
    monkeypatch.delenv("RISKFORGE_EXTERNAL_WORKER", raising=False)


def _enable_shared_sqlite(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_path = tmp_path / "rf014_acls.db"
    monkeypatch.setenv("RISKFORGE_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    monkeypatch.setenv(auth_mod.ENV_SHARED_DEPLOYMENT, "1")
    monkeypatch.delenv(auth_mod.ENV_BIND, raising=False)
    monkeypatch.delenv(auth_mod.ENV_API_TOKEN, raising=False)
    monkeypatch.setenv("RISKFORGE_API_TOKENS", TOKEN_MAP)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_local_demo_stays_unauthenticated_without_acls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_gate(monkeypatch)
    with TestClient(app) as client:
        response = client.get("/api/v1/portfolio")
    assert response.status_code == 200
    assert response.json()["id"]


def test_shared_idor_cannot_read_other_principal_stored_portfolio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _enable_shared_sqlite(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/risk/runs",
            headers=_auth(ALICE_TOKEN),
            json={"portfolio": _TINY, "run_type": "summary"},
        )
        assert created.status_code == 202, created.text
        alice_get = client.get(
            "/api/v1/portfolios/alice-private-book",
            headers=_auth(ALICE_TOKEN),
        )
        bob_get = client.get(
            "/api/v1/portfolios/alice-private-book",
            headers=_auth(BOB_TOKEN),
        )
    assert alice_get.status_code == 200
    assert alice_get.json()["id"] == "alice-private-book"
    assert bob_get.status_code == 403
    body = bob_get.json()
    _assert_error_shape(body)
    assert body["code"] == "forbidden"


def test_shared_idor_cannot_update_other_principal_stored_portfolio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _enable_shared_sqlite(monkeypatch, tmp_path)
    revised = {
        **_TINY,
        "name": "Hijacked",
        "version": 1,
        "positions": [
            {"type": "equity", "id": "eq-wipe", "symbol": "MSFT", "quantity": 1},
        ],
    }
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/risk/runs",
            headers=_auth(ALICE_TOKEN),
            json={"portfolio": _TINY, "run_type": "summary"},
        )
        assert created.status_code == 202, created.text
        bob_put = client.put(
            "/api/v1/portfolios/alice-private-book",
            headers=_auth(BOB_TOKEN),
            json=revised,
        )
        alice_put = client.put(
            "/api/v1/portfolios/alice-private-book",
            headers=_auth(ALICE_TOKEN),
            json=revised,
        )
    assert bob_put.status_code == 403
    body = bob_put.json()
    _assert_error_shape(body)
    assert body["code"] == "forbidden"
    assert alice_put.status_code == 200
    assert alice_put.json()["name"] == "Hijacked"


def test_shared_idor_cannot_read_other_principal_risk_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _enable_shared_sqlite(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/risk/runs",
            headers=_auth(ALICE_TOKEN),
            json={"portfolio": _TINY, "run_type": "summary"},
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]
        alice_run = client.get(
            f"/api/v1/risk/runs/{run_id}",
            headers=_auth(ALICE_TOKEN),
        )
        bob_run = client.get(
            f"/api/v1/risk/runs/{run_id}",
            headers=_auth(BOB_TOKEN),
        )
    assert alice_run.status_code == 200
    assert alice_run.json()["id"] == run_id
    assert bob_run.status_code == 403
    body = bob_run.json()
    _assert_error_shape(body)
    assert body["code"] == "forbidden"


def test_shared_idor_cannot_attach_other_principal_portfolio_to_new_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _enable_shared_sqlite(monkeypatch, tmp_path)
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/risk/runs",
            headers=_auth(ALICE_TOKEN),
            json={"portfolio": _TINY, "run_type": "summary"},
        )
        assert created.status_code == 202, created.text
        bob_attach = client.post(
            "/api/v1/risk/runs",
            headers=_auth(BOB_TOKEN),
            json={"portfolio": {**_TINY, "name": "Bob Cover"}, "run_type": "summary"},
        )
    assert bob_attach.status_code == 403
    body = bob_attach.json()
    _assert_error_shape(body)
    assert body["code"] == "forbidden"


def test_shared_demo_catalog_stays_readable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _enable_shared_sqlite(monkeypatch, tmp_path)
    with TestClient(app) as client:
        catalog = client.get(
            "/api/v1/portfolios/global-macro",
            headers=_auth(ALICE_TOKEN),
        )
        listed = client.get("/api/v1/portfolios", headers=_auth(BOB_TOKEN))
    assert catalog.status_code == 200
    assert catalog.json()["id"] == "global-macro"
    assert listed.status_code == 200
    ids = {row["id"] for row in listed.json()}
    assert "global-macro" in ids


def test_shared_cannot_update_demo_owned_seed_book(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _enable_shared_sqlite(monkeypatch, tmp_path)
    attacker = {
        "id": "global-macro",
        "name": "Attacker Book",
        "version": 1,
        "positions": [
            {"type": "equity", "id": "eq-wipe", "symbol": "AAPL", "quantity": 1},
        ],
    }
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/portfolios/global-macro",
            headers=_auth(ALICE_TOKEN),
            json=attacker,
        )
        after = client.get(
            "/api/v1/portfolios/global-macro",
            headers=_auth(ALICE_TOKEN),
        )
    assert response.status_code == 403
    body = response.json()
    _assert_error_shape(body)
    assert body["code"] == "forbidden"
    assert after.status_code == 200
    assert after.json()["id"] == "global-macro"
    assert after.json()["name"] != "Attacker Book"
