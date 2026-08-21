"""Stage 10.5: RiskRun provenance payload equals persisted/executed lineage.

Displayed lineage must equal stored run fields. No secrets. Release SHA is
omitted when unset rather than faked.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.market_fixtures import FixedMarketProvider, equity_spot_market
from tests.test_risk_run_api import _wait_terminal

from app.domain.models import EquityPosition, Portfolio, RiskRunStatus
from app.main import app

SECRETISH = ("password", "secret", "token", "api_key", "credential", "authorization")


@pytest.fixture
def client():
    with TestClient(app) as c:
        svc = c.app.state.portfolio_service
        previous = svc.market_data
        svc.market_data = FixedMarketProvider(equity_spot_market("NVDA", 190.0))
        try:
            yield c
        finally:
            svc.market_data = previous


@pytest.fixture
def tiny_portfolio() -> Portfolio:
    return Portfolio(
        id="prov-book",
        name="Provenance Book",
        positions=[EquityPosition(type="equity", id="eq-1", symbol="NVDA", quantity=10)],
    )


def _assert_no_secrets(payload: dict[str, Any]) -> None:
    dumped = json.dumps(payload)
    lowered_keys = {str(k).lower() for k in _walk_keys(payload)}
    for needle in SECRETISH:
        assert needle not in lowered_keys
        assert f"{needle}=" not in dumped.lower()


def _walk_keys(value: Any) -> list[Any]:
    keys: list[Any] = []
    if isinstance(value, dict):
        for key, inner in value.items():
            keys.append(key)
            keys.extend(_walk_keys(inner))
    elif isinstance(value, list):
        for inner in value:
            keys.extend(_walk_keys(inner))
    return keys


def test_get_run_provenance_matches_persisted_run_fields(client, tiny_portfolio):
    created = client.post(
        "/api/v1/risk/runs",
        json={
            "portfolio": tiny_portfolio.model_dump(mode="json"),
            "run_type": "summary",
            "request": {
                "methodology": "DELTA_GAMMA",
                "as_of": "current",
                "calculation_config": {"observations": 50, "seed": 7},
            },
        },
    )
    assert created.status_code == 202
    run_id = created.json()["id"]
    done = _wait_terminal(client, run_id)
    assert done["status"] == RiskRunStatus.COMPLETED.value

    nested = done["provenance"]
    dedicated = client.get(f"/api/v1/risk/runs/{run_id}/provenance")
    assert dedicated.status_code == 200
    payload = dedicated.json()

    assert nested == payload
    assert payload["risk_run_id"] == run_id
    assert payload["risk_run_id"] == done["id"]
    assert payload["portfolio_id"] == done["portfolio_id"] == "prov-book"
    assert payload["portfolio_version"] == done["portfolio_version"]
    assert payload["market_snapshot_id"] == done["market_snapshot_id"]
    assert payload["as_of"] == done["as_of"]
    assert payload["historical_dataset_id"] == done["historical_dataset_id"]
    assert payload["historical_dataset_version"] == done["historical_dataset_version"]
    assert payload["pricing_engine_version"] == done["pricing_engine_version"]
    assert payload["methodology"] == done["methodology"]
    assert payload["scenario_set"] == done["scenario_set"]
    assert payload["calculation_config"] == done["calculation_config"]
    assert payload["duration_seconds"] == done["duration_seconds"]
    assert payload["status"] == done["status"]
    # Do not invent a scenario-set version the run never stored.
    assert payload.get("scenario_set_version") in (None, "")
    _assert_no_secrets(payload)
    _assert_no_secrets(nested)


def test_provenance_omits_release_sha_when_unset(client, tiny_portfolio, monkeypatch):
    monkeypatch.delenv("RISKFORGE_RELEASE_SHA", raising=False)
    created = client.post(
        "/api/v1/risk/runs",
        json={
            "portfolio": tiny_portfolio.model_dump(mode="json"),
            "run_type": "summary",
            "request": {"methodology": "DELTA_GAMMA"},
        },
    )
    assert created.status_code == 202
    run_id = created.json()["id"]
    _wait_terminal(client, run_id)
    resp = client.get(f"/api/v1/risk/runs/{run_id}/provenance")
    assert resp.status_code == 200
    payload = resp.json()
    sha = payload.get("release_sha")
    # Omit rather than fake. A real git describe/SHA is allowed; placeholders are not.
    assert sha not in {"unknown", "dev", "local", ""}
    if sha is not None:
        assert all(ch.isalnum() or ch in ".-" for ch in sha)


def test_provenance_includes_release_sha_from_env(client, tiny_portfolio, monkeypatch):
    monkeypatch.setenv("RISKFORGE_RELEASE_SHA", "abc123deadbeef")
    created = client.post(
        "/api/v1/risk/runs",
        json={
            "portfolio": tiny_portfolio.model_dump(mode="json"),
            "run_type": "summary",
            "request": {"methodology": "DELTA_GAMMA"},
        },
    )
    assert created.status_code == 202
    run_id = created.json()["id"]
    _wait_terminal(client, run_id)
    payload = client.get(f"/api/v1/risk/runs/{run_id}/provenance").json()
    assert payload["release_sha"] == "abc123deadbeef"
    _assert_no_secrets(payload)
