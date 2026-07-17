"""Stage 10.2 — compare two COMPLETED RiskRuns (flagship Why Did My Risk Change).

Quant contract:
- Shock unit: relative equity/FX, relative vol, rate bp (same as historical engine).
- Sensitivity / metric unit: VaR/ES = currency loss; DV01 = currency per 1bp;
  Vega = engine vega units; stress = scenario P&L (not loss).
- Sign: positive ``delta_risk`` / ``total_change`` means the selected metric
  increased (more loss-risk for VaR/ES). Stress keeps P&L sign and is labeled.
- Currency/notional: T0/T1 portfolio currencies; no FX conversion in this report.
- Base market: T0 run's bound MarketSnapshot / as_of / dataset. T1 is comparison.
- Reconciliation: ``sum(numeric contributors) + residual == total_change``
  within abs 1e-6 or rel 1e-8 (same as test_risk_attribution.py). Hierarchy
  trade rows reconcile to the portfolio/trade bucket, not to non-additive VaR.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from tests.market_fixtures import FixedMarketProvider, equity_spots_market

from app.domain.models import (
    EquityPosition,
    MarketSnapshot,
    Portfolio,
    RiskChangeReport,
    RiskRun,
    RiskRunCalculationConfig,
    RiskRunStatus,
    VaRMethodology,
)
from app.persistence.memory_repos import InMemoryRiskRunRepository
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine
from app.risk.risk_run_compare import (
    BoundRiskRun,
    assert_risk_change_reconciles,
    explain_risk_runs,
)
from app.services.portfolio_service import PortfolioService
from app.services.risk_run_worker import RiskRunWorker

_ABS_TOL = 1e-06
_REL_TOL = 1e-08


def _ts(hour: int = 21) -> datetime:
    return datetime(2026, 7, 9, hour, 0, tzinfo=UTC)


def _tiny_book(*, spy_qty: float = 100.0, nvda_qty: float = 40.0) -> Portfolio:
    return Portfolio(
        id="cmp-book",
        name="Compare Book",
        firm="RiskForge",
        desk="Global Macro",
        strategy="Multi-Asset",
        positions=[
            EquityPosition(
                type="equity",
                id="eq-spy",
                symbol="SPY",
                quantity=spy_qty,
                sector="ETF",
                book="Equity",
            ),
            EquityPosition(
                type="equity",
                id="eq-nvda",
                symbol="NVDA",
                quantity=nvda_qty,
                sector="Technology",
                book="Tech",
            ),
        ],
    )


def _market(*, snap_id: str = "snap-t0", spy: float = 500.0, nvda: float = 120.0) -> MarketSnapshot:
    return MarketSnapshot(
        id=snap_id,
        equity_spots={"SPY": spy, "NVDA": nvda},
        equity_vols={"SPY": 0.16, "NVDA": 0.35},
        rates={"USD": 0.04},
        key_rates={"USD": {"2Y": 0.04, "10Y": 0.04}},
    )


def _completed_run(
    run_id: str,
    portfolio: Portfolio,
    market: MarketSnapshot,
    **kwargs,
) -> RiskRun:
    start = _ts()
    end = start + timedelta(seconds=2)
    return RiskRun(
        id=run_id,
        portfolio_id=portfolio.id,
        portfolio_version=portfolio.version,
        market_snapshot_id=market.id,
        status=RiskRunStatus.COMPLETED,
        started_at=start,
        completed_at=end,
        methodology=kwargs.get("methodology", VaRMethodology.DELTA_GAMMA),
        historical_dataset_id=kwargs.get("historical_dataset_id", "demo-multi-factor-history"),
        historical_dataset_version=kwargs.get("historical_dataset_version", "v1"),
        pricing_engine_version=kwargs.get("pricing_engine_version", "builtin-0.3.0"),
        calculation_config=kwargs.get("calculation_config"),
        scenario_set=list(kwargs.get("scenario_set") or []),
        as_of=kwargs.get("as_of"),
        run_type="summary",
    )


def _bound(
    run_id: str,
    portfolio: Portfolio,
    market: MarketSnapshot,
    *,
    persisted: dict[str, float] | None = None,
    **run_kwargs,
) -> BoundRiskRun:
    return BoundRiskRun(
        run=_completed_run(run_id, portfolio, market, **run_kwargs),
        portfolio=portfolio,
        market=market,
        persisted_metrics=dict(persisted or {}),
    )


def _engine() -> HistoricalRiskEngine:
    return HistoricalRiskEngine(seed=1, observations=40)


def _explain(t0: BoundRiskRun, t1: BoundRiskRun, metric: str = "var_99") -> RiskChangeReport:
    return explain_risk_runs(
        t0,
        t1,
        metric=metric,
        pricing=BuiltinPricingEngine(),
        risk_engine=_engine(),
    )


def test_incomplete_run_fails_closed() -> None:
    book = _tiny_book()
    market = _market()
    queued = RiskRun(id="r-q", portfolio_id=book.id, status=RiskRunStatus.QUEUED)
    t0 = BoundRiskRun(run=queued, portfolio=book, market=market)
    t1 = _bound("r1", book, market)
    with pytest.raises(ValueError, match="COMPLETED"):
        _explain(t0, t1)


def test_identical_runs_zero_change() -> None:
    book = _tiny_book()
    market = _market()
    t0 = _bound("r0", book, market)
    t1 = _bound("r1", book, market.model_copy(update={"id": "snap-t1"}))
    report = _explain(t0, t1)
    assert report.t0_run_id == "r0"
    assert report.t1_run_id == "r1"
    assert abs(report.total_change) < _ABS_TOL
    assert abs(report.portfolio_trade_change) < _ABS_TOL
    assert abs(report.market_change) < _ABS_TOL
    assert abs(report.residual) < _ABS_TOL
    assert_risk_change_reconciles(report)
    for item in report.factor_contributors:
        assert abs(item.delta_risk) < _ABS_TOL, item.factor_id


def test_market_only_change_typed_factor() -> None:
    book = _tiny_book()
    t0_mkt = _market(snap_id="snap-t0", spy=500.0)
    t1_mkt = _market(snap_id="snap-t1", spy=400.0)
    report = _explain(_bound("r0", book, t0_mkt), _bound("r1", book, t1_mkt))
    assert abs(report.portfolio_trade_change) < _ABS_TOL
    assert abs(report.market_change) > 1.0
    spy = next(c for c in report.factor_contributors if c.factor_id.startswith("EquitySpot:SPY"))
    assert spy.factor_type == "equity"
    assert spy.factor == "SPY"
    assert abs(spy.delta_risk) > 1.0
    for contrib in report.factor_contributors:
        if contrib.factor_id.startswith("EquitySpot:NVDA"):
            assert abs(contrib.delta_risk) < _ABS_TOL
    assert_risk_change_reconciles(report)


def test_trade_only_change() -> None:
    market = _market()
    t0 = _bound("r0", _tiny_book(spy_qty=100.0), market)
    t1 = _bound("r1", _tiny_book(spy_qty=150.0), market)
    report = _explain(t0, t1)
    assert abs(report.portfolio_trade_change) > 1.0
    assert abs(report.market_change) < _ABS_TOL
    assert_risk_change_reconciles(report)


def test_mixed_trade_and_market_change() -> None:
    t0 = _bound("r0", _tiny_book(spy_qty=100.0), _market(snap_id="a", spy=500.0))
    t1 = _bound("r1", _tiny_book(spy_qty=150.0), _market(snap_id="b", spy=400.0))
    report = _explain(t0, t1)
    assert abs(report.portfolio_trade_change) > 1.0
    assert abs(report.market_change) > 1.0
    assert_risk_change_reconciles(report)


def test_methodology_config_change_is_disclosed() -> None:
    book = _tiny_book()
    market = _market()
    t0 = _bound(
        "r0",
        book,
        market,
        methodology=VaRMethodology.DELTA_GAMMA,
        calculation_config=RiskRunCalculationConfig(observations=40, seed=1),
    )
    t1 = _bound(
        "r1",
        book,
        market.model_copy(update={"id": "snap-t1"}),
        methodology=VaRMethodology.LINEAR,
        calculation_config=RiskRunCalculationConfig(observations=80, seed=2),
        historical_dataset_id="synthetic-historical-factors",
        pricing_engine_version="quantlib-1.36",
    )
    report = _explain(t0, t1)
    disclosed = {item.lower() for item in report.disclosed_changes}
    assert any("methodology" in x for x in disclosed)
    assert any("config" in x or "calculation" in x for x in disclosed)
    assert any("dataset" in x for x in disclosed)
    assert any("engine" in x for x in disclosed)
    assert "methodology" in report.identity.changed_fields
    assert_risk_change_reconciles(report)


def test_dropped_contributor_fails_reconciliation() -> None:
    t0 = _bound("r0", _tiny_book(spy_qty=100.0), _market(snap_id="a", spy=500.0))
    t1 = _bound("r1", _tiny_book(spy_qty=150.0), _market(snap_id="b", spy=400.0))
    report = _explain(t0, t1)
    assert_risk_change_reconciles(report)
    assert report.factor_contributors, "mixed change must emit factor contributors"
    tampered = report.model_copy(update={"factor_contributors": report.factor_contributors[1:]})
    with pytest.raises(AssertionError, match="reconcil"):
        assert_risk_change_reconciles(tampered)


def test_sign_positive_when_var_increases() -> None:
    market = _market()
    t0 = _bound("r0", _tiny_book(spy_qty=50.0), market)
    t1 = _bound("r1", _tiny_book(spy_qty=200.0), market)
    report = _explain(t0, t1, metric="var_99")
    assert report.unit == "currency loss"
    assert "increased" in report.sign_convention.lower()
    assert report.total_change > 0.0
    assert report.current_risk > report.previous_risk


def test_hierarchy_trade_bucket_reconciles() -> None:
    market = _market()
    t0 = _bound("r0", _tiny_book(spy_qty=100.0, nvda_qty=40.0), market)
    t1 = _bound("r1", _tiny_book(spy_qty=180.0, nvda_qty=40.0), market)
    report = _explain(t0, t1)
    trades = [n for n in _flatten_hierarchy(report.hierarchy_contributors) if n.level == "trade"]
    assert {n.position_id for n in trades} >= {"eq-spy", "eq-nvda"}
    trade_sum = sum(n.delta_risk for n in trades)
    assert abs(trade_sum - report.portfolio_trade_change) <= max(
        _ABS_TOL, _REL_TOL * abs(report.portfolio_trade_change)
    )
    spy = next(n for n in trades if n.position_id == "eq-spy")
    nvda = next(n for n in trades if n.position_id == "eq-nvda")
    assert abs(spy.delta_risk) > 1.0
    assert abs(nvda.delta_risk) < _ABS_TOL
    levels = {n.level for n in _flatten_hierarchy(report.hierarchy_contributors)}
    assert {"firm", "desk", "book", "trade"} <= levels


def _flatten_hierarchy(nodes) -> list:
    out = []
    for node in nodes:
        out.append(node)
        out.extend(_flatten_hierarchy(node.children))
    return out


def test_prefers_persisted_headline_metrics() -> None:
    book = _tiny_book()
    market = _market()
    t0 = _bound("r0", book, market, persisted={"var_99": 111.0})
    t1 = _bound("r1", book, market.model_copy(update={"id": "t1"}), persisted={"var_99": 161.0})
    report = _explain(t0, t1)
    assert report.previous_risk == pytest.approx(111.0)
    assert report.current_risk == pytest.approx(161.0)
    assert report.total_change == pytest.approx(50.0)
    assert_risk_change_reconciles(report)


def test_stress_metric_labeled_as_pnl() -> None:
    book = _tiny_book()
    market = _market()
    report = _explain(_bound("r0", book, market), _bound("r1", _tiny_book(spy_qty=180.0), market), metric="stress")
    assert "p&l" in report.unit.lower() or "pnl" in report.unit.lower()
    assert "loss-risk" not in report.sign_convention.lower() or "p&l" in report.sign_convention.lower()
    assert_risk_change_reconciles(report)


def test_compare_api_contract_and_fail_closed() -> None:
    from app.main import app

    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        created = client.post(
            "/api/v1/risk/runs",
            json={"portfolio": book, "run_type": "summary", "request": {"methodology": "DELTA_GAMMA"}},
        )
        assert created.status_code == 202, created.text
        run_id = created.json()["id"]
        missing = client.post(
            "/api/v1/risk/runs/compare",
            json={"t0_run_id": "missing-a", "t1_run_id": "missing-b", "metric": "var_99"},
        )
        assert missing.status_code in {400, 404}

        done = _wait_terminal(client, run_id)
        assert done["status"] == "COMPLETED", done
        t1_positions = []
        for pos in book["positions"]:
            if pos.get("symbol") == "SPY" and pos.get("type") == "equity":
                t1_positions.append({**pos, "quantity": float(pos["quantity"]) * 1.5})
            else:
                t1_positions.append(pos)
        t1_book = {**book, "positions": t1_positions}
        created_t1 = client.post(
            "/api/v1/risk/runs",
            json={"portfolio": t1_book, "run_type": "summary", "request": {"methodology": "DELTA_GAMMA"}},
        )
        assert created_t1.status_code == 202, created_t1.text
        t1_id = created_t1.json()["id"]
        done_t1 = _wait_terminal(client, t1_id)
        assert done_t1["status"] == "COMPLETED", done_t1

        response = client.post(
            "/api/v1/risk/runs/compare",
            json={"t0_run_id": run_id, "t1_run_id": t1_id, "metric": "var_99"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        report = RiskChangeReport.model_validate(payload)
        assert report.t0_run_id == run_id
        assert report.t1_run_id == t1_id
        assert report.metric == "var_99"
        assert report.residual_name
        assert_risk_change_reconciles(report)

        openapi = client.app.openapi()
        assert "/api/v1/risk/change-attribution" in openapi["paths"]
        assert "/api/v1/risk/runs/compare" in openapi["paths"]
        assert "post" in openapi["paths"]["/api/v1/risk/runs/compare"]


def _wait_terminal(client: TestClient, run_id: str, *, timeout_s: float = 30.0):
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        resp = client.get(f"/api/v1/risk/runs/{run_id}")
        assert resp.status_code == 200
        last = resp.json()
        if last["status"] in {RiskRunStatus.COMPLETED.value, RiskRunStatus.FAILED.value}:
            return last
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not finish; last={last}")


def _summary_payload(portfolio_id: str) -> dict:
    return {
        "portfolio_id": portfolio_id,
        "market_value": 1.0,
        "delta": 0.0,
        "gamma": 0.0,
        "vega": 0.0,
        "dv01": 0.0,
        "fx_delta": 0.0,
        "var_95": 10.0,
        "var_99": 12.0,
        "expected_shortfall_99": 14.0,
        "methodology": "DELTA_GAMMA",
    }


def _worker_for_bind() -> RiskRunWorker:
    svc = PortfolioService(
        BuiltinPricingEngine(),
        HistoricalRiskEngine(seed=1, observations=8),
        market_data=FixedMarketProvider(
            equity_spots_market({"SPY": 500.0, "NVDA": 120.0}, vols={"SPY": 0.16, "NVDA": 0.35})
        ),
    )
    return RiskRunWorker(svc, repo=InMemoryRiskRunRepository(), max_workers=1)


def _finish(worker: RiskRunWorker, run_id: str) -> None:
    worker._with_service(lambda svc: svc.start(run_id))
    worker._with_service(
        lambda svc: svc.complete(
            run_id,
            result_type="summary",
            payload=_summary_payload("cmp-book"),
        )
    )


def _drop_bound_cache(worker: RiskRunWorker) -> None:
    with worker._portfolios_lock:
        worker._completed_portfolios.clear()
        worker._portfolios.clear()


def test_compare_does_not_attribute_mutated_live_book_on_cache_miss() -> None:
    """Cache miss + version mismatch must fail closed, not explain vs the current book.

    After a worker restart the submit-time cache is empty. Loading the mutated
    live book for both T0 and T1 would drop T0's version and attribute ~zero
    trade change even though the run identities differ.
    """
    worker = _worker_for_bind()
    t0_book = _tiny_book(spy_qty=100.0)
    t1_book = _tiny_book(spy_qty=150.0)
    try:
        t0 = worker.submit(portfolio=t0_book, run_type="summary", execute=False)
        t1 = worker.submit(portfolio=t1_book, run_type="summary", execute=False)
        assert t0.portfolio_version == 1
        assert t1.portfolio_version == 1
        _finish(worker, t0.id)
        _finish(worker, t1.id)

        live = _tiny_book(spy_qty=999.0).model_copy(update={"version": 2})
        worker._load_portfolio = lambda _pid: live  # type: ignore[method-assign]
        _drop_bound_cache(worker)

        with pytest.raises(ValueError, match="portfolio_version"):
            worker.compare_runs(t0.id, t1.id)
    finally:
        worker.shutdown(wait=False)


def test_bound_portfolio_uses_live_book_when_versions_match() -> None:
    worker = _worker_for_bind()
    book = _tiny_book(spy_qty=100.0)
    try:
        view = worker.submit(portfolio=book, run_type="summary", execute=False)
        run = worker._with_service(lambda svc: svc.get(view.id))
        live = _tiny_book(spy_qty=100.0)
        assert live.version == run.portfolio_version == 1
        worker._load_portfolio = lambda _pid: live  # type: ignore[method-assign]
        _drop_bound_cache(worker)
        bound = worker._bound_portfolio(run)
        assert bound.version == 1
        assert bound.positions[0].quantity == 100.0
    finally:
        worker.shutdown(wait=False)


def test_bound_portfolio_fails_closed_when_run_version_missing() -> None:
    worker = _worker_for_bind()
    try:
        run = _completed_run("legacy-unversioned", _tiny_book(), _market())
        run = run.model_copy(update={"portfolio_version": None})
        worker._load_portfolio = lambda _pid: _tiny_book()  # type: ignore[method-assign]
        with pytest.raises(ValueError, match="portfolio_version"):
            worker._bound_portfolio(run)
    finally:
        worker.shutdown(wait=False)
