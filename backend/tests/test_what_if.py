"""M2.9 What-if API — hypothetical add/remove/modify without mutating the request book."""

from __future__ import annotations

import math

from fastapi.testclient import TestClient

from app.domain.models import EquityPosition, VaRMethodology, WhatIfRequest
from app.main import app
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.incremental_var import apply_what_if_changes
from app.sample import SAMPLE_PORTFOLIO
from app.services.portfolio_service import PortfolioService

_TOL = 1e-9
_OBS = 80


def _hypo() -> EquityPosition:
    return EquityPosition(
        type="equity",
        id="eq-whatif",
        symbol="SPY",
        quantity=400.0,
        price=565.0,
        sector="ETF",
    )


def test_service_what_if_returns_before_after_incremental_and_deltas():
    svc = PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=7, observations=_OBS),
    )
    request = WhatIfRequest(
        portfolio=SAMPLE_PORTFOLIO,
        changes=[{"operation": "add", "position": _hypo()}],
        methodology=VaRMethodology.DELTA_GAMMA,
    )
    # Snapshot original ids to prove service does not mutate input.
    original_ids = [p.id for p in request.portfolio.positions]
    report = svc.what_if(request)
    assert [p.id for p in request.portfolio.positions] == original_ids
    assert "eq-whatif" not in original_ids

    assert report.methodology == VaRMethodology.DELTA_GAMMA
    assert report.before.var_99 >= 0.0
    assert report.after.var_99 >= 0.0
    assert math.isclose(
        report.incremental.var_99,
        report.after.var_99 - report.before.var_99,
        abs_tol=_TOL,
    )
    assert math.isclose(
        report.incremental.expected_shortfall_99,
        report.after.expected_shortfall_99 - report.before.expected_shortfall_99,
        abs_tol=_TOL,
    )
    assert any(c.delta != 0.0 for c in report.changed_factor_exposures)
    assert len(report.changed_stress_losses) >= 1
    for s in report.changed_stress_losses:
        assert math.isclose(s.delta_pnl, s.after_pnl - s.before_pnl, abs_tol=_TOL)


def test_what_if_api_add_trade():
    client = TestClient(app)
    portfolio = client.get("/portfolio").json()
    body = {
        "portfolio": portfolio,
        "methodology": "DELTA_GAMMA",
        "changes": [
            {
                "operation": "add",
                "position": {
                    "type": "equity",
                    "id": "eq-whatif",
                    "symbol": "SPY",
                    "quantity": 400,
                    "price": 565.0,
                    "sector": "ETF",
                },
            }
        ],
    }
    response = client.post("/risk/what-if", json=body)
    assert response.status_code == 200
    payload = response.json()
    assert payload["methodology"] == "DELTA_GAMMA"
    assert "before" in payload and "after" in payload and "incremental" in payload
    assert math.isclose(
        payload["incremental"]["var_99"],
        payload["after"]["var_99"] - payload["before"]["var_99"],
        abs_tol=_TOL,
    )
    assert "changed_factor_exposures" in payload
    assert "changed_stress_losses" in payload
    # Persisted sample book unchanged via GET
    still = client.get("/portfolio").json()
    assert all(p["id"] != "eq-whatif" for p in still["positions"])


def test_what_if_api_methodology_query_override():
    client = TestClient(app)
    portfolio = client.get("/portfolio").json()
    body = {
        "portfolio": portfolio,
        "methodology": "DELTA_GAMMA",
        "changes": [{"operation": "remove", "position_id": "eq-spy"}],
    }
    response = client.post("/risk/what-if?methodology=LINEAR", json=body)
    assert response.status_code == 200
    assert response.json()["methodology"] == "LINEAR"


def test_what_if_api_rejects_bad_remove():
    client = TestClient(app)
    portfolio = client.get("/portfolio").json()
    body = {
        "portfolio": portfolio,
        "changes": [{"operation": "remove", "position_id": "does-not-exist"}],
    }
    response = client.post("/risk/what-if", json=body)
    assert response.status_code == 400


def test_what_if_remove_matches_apply_helper():
    svc = PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=7, observations=_OBS),
    )
    request = WhatIfRequest(
        portfolio=SAMPLE_PORTFOLIO,
        changes=[{"operation": "remove", "position_id": "opt-spy-put"}],
    )
    report = svc.what_if(request)
    after_pf = apply_what_if_changes(
        SAMPLE_PORTFOLIO, [{"operation": "remove", "position_id": "opt-spy-put"}]
    )
    direct = svc.summary(after_pf, methodology=VaRMethodology.DELTA_GAMMA)
    assert math.isclose(report.after.var_99, direct.var_99, abs_tol=_TOL)
