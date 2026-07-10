"""R0.10.3 / RF-015 leftover: HEAVY work must not monopolize the request thread.

When Compose / production-shaped deploys set ``RISKFORGE_EXTERNAL_WORKER=1``
(or ``RISKFORGE_HEAVY_INLINE=0``), HEAVY ``/risk/*`` handlers refuse
request-thread compute and point clients at ``POST /risk/runs``.
INTERACTIVE LINEAR / DELTA_GAMMA summary, stress scenario GETs, and
``/limits/drilldown`` stay sync.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.backpressure import RISK_RUNS_PATH, heavy_inline_allowed
from app.main import app

PUBLIC_BAD_REQUEST = "Invalid request"
RISK_RUNS = "/risk/runs"


def _assert_refused_inline(response) -> None:
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "bad_request"
    assert body["message"] == PUBLIC_BAD_REQUEST
    assert isinstance(body["details"], dict)
    assert body["details"]["use"] == RISK_RUNS


def test_full_revaluation_summary_refused_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        response = client.post(
            "/api/v1/risk/summary",
            params={"methodology": "FULL_REVALUATION"},
            json=book,
        )
        _assert_refused_inline(response)


def test_full_revaluation_summary_refused_on_legacy_mount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/portfolio").json()
        response = client.post(
            "/risk/summary",
            params={"methodology": "FULL_REVALUATION"},
            json=book,
        )
        _assert_refused_inline(response)


def test_dashboard_refused_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        response = client.post("/api/v1/risk/dashboard")
        _assert_refused_inline(response)


def test_dashboard_refused_when_heavy_inline_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RISKFORGE_EXTERNAL_WORKER", raising=False)
    monkeypatch.setenv("RISKFORGE_HEAVY_INLINE", "0")
    with TestClient(app) as client:
        response = client.post("/risk/dashboard")
        _assert_refused_inline(response)


def test_heavy_inline_allowed_defaults_and_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RISKFORGE_EXTERNAL_WORKER", raising=False)
    monkeypatch.delenv("RISKFORGE_HEAVY_INLINE", raising=False)
    assert heavy_inline_allowed() is True
    assert RISK_RUNS_PATH == "/risk/runs"

    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    assert heavy_inline_allowed() is False

    monkeypatch.delenv("RISKFORGE_EXTERNAL_WORKER", raising=False)
    monkeypatch.setenv("RISKFORGE_HEAVY_INLINE", "0")
    assert heavy_inline_allowed() is False


@pytest.mark.parametrize("methodology", ["LINEAR", "DELTA_GAMMA"])
def test_interactive_summary_stays_sync_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
    methodology: str,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        response = client.post(
            "/api/v1/risk/summary",
            params={"methodology": methodology},
            json=book,
        )
        assert response.status_code == 200, response.text
        assert response.json()["portfolio_id"] == book["id"]


# Leftover HEAVY handlers in risk.py (R0.10.3 review leftover). The route
# itself is HEAVY — LINEAR / default methodology is still refused.
_LEFTOVER_HEAVY_PORTFOLIO_PATHS = (
    "/api/v1/risk/var",
    "/api/v1/risk/es",
    "/api/v1/risk/var/compare",
    "/api/v1/risk/hierarchy",
    "/api/v1/risk/contributors",
    "/risk/var",
    "/risk/hierarchy",
)


@pytest.mark.parametrize("path", _LEFTOVER_HEAVY_PORTFOLIO_PATHS)
def test_leftover_heavy_portfolio_routes_refused_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        response = client.post(path, json=book)
        _assert_refused_inline(response)


def test_var_linear_refused_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``POST /risk/var`` is HEAVY even with LINEAR (unlike summary)."""
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        response = client.post(
            "/api/v1/risk/var",
            params={"methodology": "LINEAR"},
            json=book,
        )
        _assert_refused_inline(response)


def test_what_if_refused_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        body = {
            "portfolio": book,
            "methodology": "DELTA_GAMMA",
            "changes": [{"operation": "remove", "position_id": book["positions"][0]["id"]}],
        }
        response = client.post("/api/v1/risk/what-if", json=body)
        _assert_refused_inline(response)


def test_query_refused_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        response = client.post(
            "/api/v1/risk/query",
            json={"portfolio": book, "question": "What is 99% VaR?"},
        )
        _assert_refused_inline(response)


def test_leftover_heavy_refused_when_heavy_inline_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RISKFORGE_EXTERNAL_WORKER", raising=False)
    monkeypatch.setenv("RISKFORGE_HEAVY_INLINE", "0")
    with TestClient(app) as client:
        book = client.get("/portfolio").json()
        response = client.post("/risk/es", json=book)
        _assert_refused_inline(response)


def test_interactive_factors_stays_sync_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        response = client.post("/api/v1/risk/factors", json=book)
        assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# HEAVY stress / attribution / limits leftovers (R0.10.3 slice)
# ---------------------------------------------------------------------------

_STRESS_ATTR_LIMITS_PORTFOLIO_PATHS = (
    "/api/v1/risk/stress",
    "/api/v1/risk/stress/evaluate",
    "/api/v1/risk/attribution/demo",
    "/api/v1/risk/limits",
    "/risk/stress",
    "/risk/limits",
)


@pytest.mark.parametrize("path", _STRESS_ATTR_LIMITS_PORTFOLIO_PATHS)
def test_stress_attr_limits_portfolio_routes_refused_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        response = client.post(path, json=book)
        _assert_refused_inline(response)


def test_stress_custom_routes_refused_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    scenario = {
        "name": "Custom",
        "equity_shock": -0.1,
        "vol_shock": 0.0,
        "rates_shift_bps": 0.0,
        "fx_shock": 0.0,
        "max_loss_pct": 0.02,
    }
    formal_scenario = {
        "id": "custom-formal",
        "name": "Custom",
        "category": "hypothetical",
        "shocks": [
            {
                "factor_type": "equity",
                "key": "SPY",
                "amount": -0.10,
                "bucket": "SPY",
            }
        ],
        "max_loss_pct": 0.02,
    }
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        legacy_body = {"portfolio": book, "scenarios": [scenario]}
        formal_body = {"portfolio": book, "scenarios": [formal_scenario]}
        for path in (
            "/api/v1/risk/stress/custom",
            "/api/v1/risk/stress/evaluate/custom",
            "/risk/stress/custom",
        ):
            _assert_refused_inline(client.post(path, json=legacy_body))
        for path in (
            "/api/v1/risk/stress/formal/custom",
            "/api/v1/risk/stress/formal/evaluate/custom",
        ):
            _assert_refused_inline(client.post(path, json=formal_body))


def test_stress_reverse_and_compare_refused_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        hedged = {
            **book,
            "id": f"{book['id']}-hedged",
            "positions": [
                {
                    **book["positions"][0],
                    "quantity": float(book["positions"][0]["quantity"]) * 0.5,
                },
                *book["positions"][1:],
            ],
        }
        _assert_refused_inline(
            client.post(
                "/api/v1/risk/stress/reverse",
                json={
                    "portfolio": book,
                    "target_loss_pct": 0.05,
                    "factor": "equity",
                },
            )
        )
        _assert_refused_inline(
            client.post(
                "/risk/stress/reverse/multi",
                json={
                    "portfolio": book,
                    "target_loss_pct": 0.05,
                    "factors": ["equity", "vol"],
                },
            )
        )
        _assert_refused_inline(
            client.post(
                "/api/v1/risk/stress/compare",
                json={
                    "portfolio": book,
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
        )
        _assert_refused_inline(
            client.post(
                "/api/v1/risk/stress/formal/compare",
                json={
                    "portfolio": book,
                    "hedged_portfolio": hedged,
                    "scenarios": [
                        {
                            "id": "Equity -10%",
                            "name": "Equity -10%",
                            "category": "factor",
                            "shocks": [
                                {
                                    "factor_type": "equity",
                                    "key": "SPY",
                                    "amount": -0.10,
                                    "bucket": "SPY",
                                }
                            ],
                        }
                    ],
                    "methodology": "DELTA_GAMMA",
                },
            )
        )


def test_attribution_routes_refused_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        _assert_refused_inline(
            client.post(
                "/api/v1/risk/attribution",
                json={"previous_portfolio": book, "current_portfolio": book},
            )
        )
        _assert_refused_inline(
            client.post(
                "/risk/change-attribution",
                json={
                    "previous_portfolio": book,
                    "current_portfolio": book,
                    "metric": "var_99",
                    "methodology": "DELTA_GAMMA",
                },
            )
        )
        _assert_refused_inline(
            client.post(
                "/api/v1/risk/runs/compare",
                json={"t0_run_id": "run-t0", "t1_run_id": "run-t1", "metric": "var_99"},
            )
        )


def test_stress_attr_limits_refused_when_heavy_inline_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RISKFORGE_EXTERNAL_WORKER", raising=False)
    monkeypatch.setenv("RISKFORGE_HEAVY_INLINE", "0")
    with TestClient(app) as client:
        book = client.get("/portfolio").json()
        _assert_refused_inline(client.post("/risk/stress", json=book))
        _assert_refused_inline(client.post("/api/v1/risk/limits", json=book))


def test_interactive_stress_scenarios_stay_sync_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        default = client.get("/api/v1/risk/stress/scenarios")
        formal = client.get("/api/v1/risk/stress/scenarios/formal")
        assert default.status_code == 200, default.text
        assert formal.status_code == 200, formal.text
        assert formal.json() == default.json()
        assert "shocks" in default.json()[0]
        # Legacy mount also stays interactive.
        assert client.get("/risk/stress/scenarios").status_code == 200


def test_interactive_limits_drilldown_stays_sync_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        payload = {
            "portfolio": book,
            "metric": "var_99",
            "breaches_only": False,
            "top_n": 2,
        }
        response = client.post("/api/v1/risk/limits/drilldown", json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["portfolio_id"] == book["id"]
        legacy = client.post("/risk/limits/drilldown", json=payload)
        assert legacy.status_code == 200, legacy.text
