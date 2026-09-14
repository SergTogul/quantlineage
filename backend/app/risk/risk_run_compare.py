"""Two-RiskRun risk-change explain (Stage 10.2 flagship).

Separate from the portfolio-pair waterfall in :mod:`app.risk.risk_attribution`.
This module compares two immutable COMPLETED :class:`~app.domain.models.RiskRun`
states and attributes a selected metric.

Methodology
-----------
VaR / ES
    Bridging waterfall on :class:`~app.risk.historical.HistoricalRiskEngine`
    using T0's declared engine/dataset/methodology: trade bridge (closed →
    resize → new) on the T0 market, then sequential typed-factor market
    replacements toward T1. Residual absorbs order/correlation effects and any
    T1 methodology/config/dataset/engine difference (those are disclosed, not
    silently mixed into T0 execution). This is **not** a certified Euler
    allocation of historical quantile VaR.

DV01 / Vega
    Same bridge on additive greeks from ``HistoricalRiskEngine.calculate``
    (currency per 1bp / engine vega units). Residual should be near zero when
    identity is unchanged.

Stress
    Scenario P&L diffs (not loss) for each run's declared ``scenario_set``
    (fail closed if empty or unknown). Sign is P&L; the report unit/sign
    fields label that explicitly.

Quant contract
--------------
- Shock unit: relative equity/FX, relative vol, rate decimal (MarketSnapshot.bump).
- Sensitivity unit: VaR/ES currency loss; DV01 currency per 1bp; Vega engine units;
  stress scenario P&L.
- Sign: positive ``delta_risk`` / ``total_change`` means the selected metric
  increased (more loss-risk for VaR/ES). DV01/Vega are the metric increase
  in their native units. Stress keeps P&L sign.
- Currency/notional: T0/T1 portfolio currencies; no FX conversion here.
- Base market: T0 run's bound snapshot / as_of / dataset. T1 is comparison.
- Reconciliation: ``portfolio_trade_change + market_change + residual ==
  total_change`` (abs 1e-6 or rel 1e-8). Factor contributors sum to
  ``market_change``. Hierarchy trade rows sum to ``portfolio_trade_change``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping

from app.domain.models import (
    MarketSnapshot,
    Portfolio,
    Position,
    RiskChangeFactorContributor,
    RiskChangeHierarchyContributor,
    RiskChangeItem,
    RiskChangeMetric,
    RiskChangeReport,
    RiskRun,
    RiskRunIdentityDiff,
    RiskRunIdentitySnapshot,
    RiskRunStatus,
    VaRMethodology,
    as_of_wire,
)
from app.interfaces.pricing import PricingEngine
from app.market.history.data_mode import data_source_label
from app.risk.factor_types import (
    EquitySpot,
    EquityVol,
    FXSpot,
    FXVol,
    RateZero,
    RiskFactor,
    factor_column_id,
)
from app.risk.historical import HistoricalRiskEngine
from app.risk.scenario_model import BroadcastScenarioDefinition, expand_broadcast_definition
from app.risk.stress import DEFAULT_SCENARIOS, THREAT_SCENARIOS, StressEngine

_ABS_TOL = 1e-06
_REL_TOL = 1e-08

_VAR_ES: frozenset[str] = frozenset({"var_99", "var_95", "expected_shortfall_99"})
_DISCLOSE_FIELDS = (
    "methodology",
    "calculation_config",
    "historical_dataset_id",
    "historical_dataset_version",
    "pricing_engine_version",
    "scenario_set",
)


@dataclass(frozen=True)
class BoundRiskRun:
    """A RiskRun plus the book and snapshot it executed against."""

    run: RiskRun
    portfolio: Portfolio
    market: MarketSnapshot
    persisted_metrics: Mapping[str, float] = field(default_factory=dict)


def _close(actual: float, expected: float, *, abs_tol: float = _ABS_TOL, rel_tol: float = _REL_TOL) -> bool:
    return abs(actual - expected) <= max(abs_tol, rel_tol * abs(expected))


def _flatten_hierarchy(
    nodes: list[RiskChangeHierarchyContributor],
) -> list[RiskChangeHierarchyContributor]:
    out: list[RiskChangeHierarchyContributor] = []
    for node in nodes:
        out.append(node)
        out.extend(_flatten_hierarchy(node.children))
    return out


def assert_risk_change_reconciles(
    report: RiskChangeReport,
    *,
    abs_tol: float = _ABS_TOL,
    rel_tol: float = _REL_TOL,
) -> None:
    """Fail if buckets / factors / trade hierarchy do not reconcile."""

    bucket = report.portfolio_trade_change + report.market_change + report.residual
    if not _close(bucket, report.total_change, abs_tol=abs_tol, rel_tol=rel_tol):
        raise AssertionError(
            f"reconciliation failed: trade {report.portfolio_trade_change} + "
            f"market {report.market_change} + residual {report.residual} != "
            f"total {report.total_change}"
        )
    factor_sum = sum(c.delta_risk for c in report.factor_contributors)
    if not _close(factor_sum, report.market_change, abs_tol=abs_tol, rel_tol=rel_tol):
        raise AssertionError(
            f"reconciliation failed: factor contributors {factor_sum} != "
            f"market_change {report.market_change}"
        )
    trades = [n for n in _flatten_hierarchy(report.hierarchy_contributors) if n.level == "trade"]
    if trades:
        trade_sum = sum(n.delta_risk for n in trades)
        if not _close(
            trade_sum, report.portfolio_trade_change, abs_tol=abs_tol, rel_tol=rel_tol
        ):
            raise AssertionError(
                f"reconciliation failed: hierarchy trades {trade_sum} != "
                f"portfolio_trade_change {report.portfolio_trade_change}"
            )


def _clone_portfolio(template: Portfolio, positions: list[Position], *, suffix: str) -> Portfolio:
    return Portfolio(
        id=f"{template.id}:{suffix}",
        name=template.name,
        positions=list(positions),
        firm=template.firm,
        desk=template.desk,
        strategy=template.strategy,
        version=template.version,
    )


def _unit(metric: str) -> str:
    if metric in _VAR_ES:
        return "currency loss"
    if metric == "dv01":
        return "currency per 1bp"
    if metric == "vega":
        return "engine vega units"
    if metric == "stress":
        return "scenario P&L (not loss)"
    return "currency"


def _sign_convention(metric: str) -> str:
    if metric == "stress":
        return "positive total_change means scenario P&L increased (P&L sign, not loss)"
    if metric == "dv01":
        return "positive total_change means DV01 increased (currency per 1bp)"
    if metric == "vega":
        return "positive total_change means vega increased (engine vega units)"
    return "positive total_change means the selected metric increased (more loss-risk for VaR/ES)"


def _methodology(run: RiskRun) -> VaRMethodology:
    return run.methodology or VaRMethodology.DELTA_GAMMA


def _scenario_library() -> dict[str, BroadcastScenarioDefinition]:
    out: dict[str, BroadcastScenarioDefinition] = {}
    for item in (*DEFAULT_SCENARIOS, *THREAT_SCENARIOS):
        if item.id:
            out[item.id] = item
    return out


def _resolve_stress_scenarios(run: RiskRun, market: MarketSnapshot) -> list:
    ids = list(run.scenario_set)
    if not ids:
        raise ValueError(f"run {run.id} has empty scenario_set; cannot compute stress")
    library = _scenario_library()
    resolved = []
    for sid in ids:
        defn = library.get(sid)
        if defn is None:
            raise ValueError(f"unknown scenario {sid!r} in run {run.id} scenario_set")
        resolved.append(expand_broadcast_definition(defn, market))
    if not resolved:
        raise ValueError(f"run {run.id} scenario_set resolved empty")
    return resolved


def _metric_value(
    *,
    engine: HistoricalRiskEngine,
    pricing: PricingEngine,
    portfolio: Portfolio,
    market: MarketSnapshot,
    methodology: VaRMethodology,
    metric: str,
    run: RiskRun,
) -> float:
    if metric == "stress":
        scenarios = _resolve_stress_scenarios(run, market)
        rows = StressEngine().run(portfolio, pricing, scenarios, market=market)
        if not rows:
            raise ValueError(f"run {run.id} stress produced no scenario P&L")
        return float(rows[0].pnl)
    summary = engine.calculate(portfolio, pricing, methodology=methodology, market=market)
    return float(getattr(summary, metric))


def _identity_snapshot(bound: BoundRiskRun) -> RiskRunIdentitySnapshot:
    run = bound.run
    as_of = as_of_wire(run.as_of) if run.as_of is not None else None
    methodology = run.methodology.value if run.methodology is not None else None
    return RiskRunIdentitySnapshot(
        run_id=run.id,
        portfolio_id=run.portfolio_id,
        portfolio_version=run.portfolio_version,
        market_snapshot_id=run.market_snapshot_id,
        as_of=as_of,
        historical_dataset_id=run.historical_dataset_id,
        historical_dataset_version=run.historical_dataset_version,
        data_source_label=data_source_label(
            run.historical_dataset_id, run.historical_dataset_version
        ),
        pricing_engine_version=run.pricing_engine_version,
        methodology=methodology,
        scenario_set=list(run.scenario_set),
        calculation_config=run.calculation_config,
        status=run.status,
    )


def _identity_diff(t0: BoundRiskRun, t1: BoundRiskRun) -> RiskRunIdentityDiff:
    left = _identity_snapshot(t0)
    right = _identity_snapshot(t1)
    fields = (
        "portfolio_id",
        "portfolio_version",
        "market_snapshot_id",
        "as_of",
        "historical_dataset_id",
        "historical_dataset_version",
        "pricing_engine_version",
        "methodology",
        "scenario_set",
        "calculation_config",
    )
    changed: list[str] = []
    dump_l = left.model_dump()
    dump_r = right.model_dump()
    for name in fields:
        if dump_l.get(name) != dump_r.get(name):
            changed.append(name)
    return RiskRunIdentityDiff(t0=left, t1=right, changed_fields=changed)


def _changed_factors(t0: MarketSnapshot, t1: MarketSnapshot) -> list[RiskFactor]:
    factors: list[RiskFactor] = []
    for symbol in sorted(set(t0.equity_spots) | set(t1.equity_spots)):
        if t0.equity_spots.get(symbol) != t1.equity_spots.get(symbol):
            factors.append(EquitySpot(symbol))
    for symbol in sorted(set(t0.equity_vols) | set(t1.equity_vols)):
        if t0.equity_vols.get(symbol) != t1.equity_vols.get(symbol):
            factors.append(EquityVol(underlying=symbol))
    for pair in sorted(set(t0.fx_spots) | set(t1.fx_spots)):
        if t0.fx_spots.get(pair) != t1.fx_spots.get(pair):
            factors.append(FXSpot(pair))
    for pair in sorted(set(t0.fx_vols) | set(t1.fx_vols)):
        if t0.fx_vols.get(pair) != t1.fx_vols.get(pair):
            factors.append(FXVol(pair=pair))
    for ccy in sorted(set(t0.rates) | set(t1.rates)):
        if t0.rates.get(ccy) != t1.rates.get(ccy):
            factors.append(RateZero(ccy, "PARALLEL"))
    tenors: set[tuple[str, str]] = set()
    for ccy, bucket in t0.key_rates.items():
        for tenor in bucket:
            tenors.add((ccy, tenor))
    for ccy, bucket in t1.key_rates.items():
        for tenor in bucket:
            tenors.add((ccy, tenor))
    for ccy, tenor in sorted(tenors):
        left = (t0.key_rates.get(ccy) or {}).get(tenor)
        right = (t1.key_rates.get(ccy) or {}).get(tenor)
        if left != right:
            factors.append(RateZero(ccy, tenor))
    return factors


def _align_factor(running: MarketSnapshot, target: MarketSnapshot, factor: RiskFactor) -> MarketSnapshot:
    if isinstance(factor, EquitySpot):
        base = running.equity_spots.get(factor.symbol)
        nxt = target.equity_spots.get(factor.symbol)
        if base and nxt is not None and base != 0:
            return running.bump(factor, (float(nxt) - float(base)) / float(base))
        spots = dict(running.equity_spots)
        if nxt is not None:
            spots[factor.symbol] = float(nxt)
        elif factor.symbol in spots:
            del spots[factor.symbol]
        return running.model_copy(update={"equity_spots": spots, "id": f"{running.id}:{factor.key}"})
    if isinstance(factor, EquityVol):
        base = running.equity_vols.get(factor.underlying)
        nxt = target.equity_vols.get(factor.underlying)
        if base and nxt is not None and base != 0:
            return running.bump(factor, (float(nxt) - float(base)) / float(base))
        vols = dict(running.equity_vols)
        if nxt is not None:
            vols[factor.underlying] = float(nxt)
        return running.model_copy(update={"equity_vols": vols, "id": f"{running.id}:{factor.key}"})
    if isinstance(factor, FXSpot):
        base = running.fx_spots.get(factor.pair)
        nxt = target.fx_spots.get(factor.pair)
        if base and nxt is not None and base != 0:
            return running.bump(factor, (float(nxt) - float(base)) / float(base))
        spots = dict(running.fx_spots)
        if nxt is not None:
            spots[factor.pair] = float(nxt)
        return running.model_copy(update={"fx_spots": spots, "id": f"{running.id}:{factor.key}"})
    if isinstance(factor, FXVol):
        base = running.fx_vols.get(factor.pair)
        nxt = target.fx_vols.get(factor.pair)
        if base and nxt is not None and base != 0:
            return running.bump(factor, (float(nxt) - float(base)) / float(base))
        vols = dict(running.fx_vols)
        if nxt is not None:
            vols[factor.pair] = float(nxt)
        return running.model_copy(update={"fx_vols": vols, "id": f"{running.id}:{factor.key}"})
    if isinstance(factor, RateZero):
        if factor.tenor in {"PARALLEL", "ALL"}:
            # Copy scalar rates only. MarketSnapshot.bump(PARALLEL) also shifts
            # every key_rates[ccy] tenor; that would leak a spurious key-rate
            # shock into this isolated factor step.
            rates = dict(running.rates)
            nxt = target.rates.get(factor.currency)
            if nxt is not None:
                rates[factor.currency] = float(nxt)
            elif factor.currency in rates:
                del rates[factor.currency]
            return running.model_copy(update={"rates": rates, "id": f"{running.id}:{factor.key}"})
        base = (running.key_rates.get(factor.currency) or {}).get(factor.tenor)
        nxt = (target.key_rates.get(factor.currency) or {}).get(factor.tenor)
        if base is not None and nxt is not None:
            return running.bump(factor, float(nxt) - float(base))
        key_rates = {ccy: dict(tenors) for ccy, tenors in running.key_rates.items()}
        bucket = dict(key_rates.get(factor.currency) or {})
        if nxt is not None:
            bucket[factor.tenor] = float(nxt)
        key_rates[factor.currency] = bucket
        return running.model_copy(update={"key_rates": key_rates, "id": f"{running.id}:{factor.key}"})
    raise TypeError(f"unsupported risk factor type: {type(factor)!r}")


def _position_changed(previous: Position, current: Position) -> bool:
    return previous.model_dump(mode="json") != current.model_dump(mode="json")


def _desk_of(portfolio: Portfolio, position: Position) -> str:
    return getattr(position, "desk", None) or portfolio.desk


def _book_of(position: Position) -> str:
    return getattr(position, "book", None) or "Book"


def _trade_contributor(portfolio: Portfolio, position: Position, delta: float) -> RiskChangeHierarchyContributor:
    desk = _desk_of(portfolio, position)
    book = _book_of(position)
    path = f"{portfolio.firm}/{desk}/{book}/{position.id}"
    return RiskChangeHierarchyContributor(
        level="trade",
        name=position.id,
        path=path,
        delta_risk=delta,
        position_id=position.id,
    )


def _hierarchy_tree(
    portfolio: Portfolio,
    trades: list[RiskChangeHierarchyContributor],
) -> list[RiskChangeHierarchyContributor]:
    by_book: dict[tuple[str, str], list[RiskChangeHierarchyContributor]] = defaultdict(list)
    for trade in trades:
        parts = trade.path.split("/")
        desk = parts[1] if len(parts) > 1 else portfolio.desk
        book = parts[2] if len(parts) > 2 else _book_of(next(
            (p for p in portfolio.positions if p.id == trade.position_id),
            portfolio.positions[0],
        ))
        by_book[(desk, book)].append(trade)

    by_desk: dict[str, list[RiskChangeHierarchyContributor]] = defaultdict(list)
    for (desk, book), book_trades in sorted(by_book.items()):
        book_delta = sum(t.delta_risk for t in book_trades)
        by_desk[desk].append(
            RiskChangeHierarchyContributor(
                level="book",
                name=book,
                path=f"{portfolio.firm}/{desk}/{book}",
                delta_risk=book_delta,
                children=list(book_trades),
            )
        )

    desks: list[RiskChangeHierarchyContributor] = []
    for desk, books in sorted(by_desk.items()):
        desk_delta = sum(b.delta_risk for b in books)
        desks.append(
            RiskChangeHierarchyContributor(
                level="desk",
                name=desk,
                path=f"{portfolio.firm}/{desk}",
                delta_risk=desk_delta,
                children=books,
            )
        )
    firm_delta = sum(d.delta_risk for d in desks)
    return [
        RiskChangeHierarchyContributor(
            level="firm",
            name=portfolio.firm,
            path=portfolio.firm,
            delta_risk=firm_delta,
            children=desks,
        )
    ]


def _headline(bound: BoundRiskRun, metric: str, computed: float) -> float:
    persisted = bound.persisted_metrics.get(metric)
    if persisted is not None:
        return float(persisted)
    return computed


def explain_risk_runs(
    t0: BoundRiskRun,
    t1: BoundRiskRun,
    *,
    metric: RiskChangeMetric | str = "var_99",
    pricing: PricingEngine,
    risk_engine: HistoricalRiskEngine | None = None,
    t1_risk_engine: HistoricalRiskEngine | None = None,
    t1_pricing: PricingEngine | None = None,
) -> RiskChangeReport:
    """Compare two COMPLETED RiskRuns; fail closed otherwise."""

    if t0.run.status != RiskRunStatus.COMPLETED or t1.run.status != RiskRunStatus.COMPLETED:
        raise ValueError("both RiskRuns must be COMPLETED")
    if risk_engine is None:
        raise ValueError("risk_engine is required; refuse bare HistoricalRiskEngine() default")
    metric_name: str = str(metric)
    if metric_name not in {
        "var_99",
        "var_95",
        "expected_shortfall_99",
        "dv01",
        "vega",
        "stress",
    }:
        raise ValueError(f"unsupported metric: {metric_name}")

    engine_t0 = risk_engine
    engine_t1 = t1_risk_engine or engine_t0
    pricing_t1 = t1_pricing or pricing
    meth_t0 = _methodology(t0.run)
    meth_t1 = _methodology(t1.run)

    def value(
        portfolio: Portfolio,
        market: MarketSnapshot,
        *,
        engine=engine_t0,
        methodology=meth_t0,
        pricing_engine=pricing,
        run: RiskRun = t0.run,
    ) -> float:
        return _metric_value(
            engine=engine,
            pricing=pricing_engine,
            portfolio=portfolio,
            market=market,
            methodology=methodology,
            metric=metric_name,
            run=run,
        )

    computed_prev = value(t0.portfolio, t0.market)
    computed_curr = value(
        t1.portfolio,
        t1.market,
        engine=engine_t1,
        methodology=meth_t1,
        pricing_engine=pricing_t1,
        run=t1.run,
    )
    previous_risk = _headline(t0, metric_name, computed_prev)
    current_risk = _headline(t1, metric_name, computed_curr)
    total_change = current_risk - previous_risk

    prev_by_id = {p.id: p for p in t0.portfolio.positions}
    curr_by_id = {p.id: p for p in t1.portfolio.positions}
    closed_ids = sorted(set(prev_by_id) - set(curr_by_id))
    common_ids = sorted(set(prev_by_id) & set(curr_by_id))
    new_ids = sorted(set(curr_by_id) - set(prev_by_id))

    items: list[RiskChangeItem] = []
    trade_nodes: list[RiskChangeHierarchyContributor] = []
    running_positions = list(t0.portfolio.positions)
    running_pf = t0.portfolio
    running_risk = computed_prev

    for pid in closed_ids:
        nxt_positions = [p for p in running_positions if p.id != pid]
        nxt = _clone_portfolio(t0.portfolio, nxt_positions, suffix=f"no-{pid}")
        risk_after = value(nxt, t0.market)
        delta = risk_after - running_risk
        items.append(RiskChangeItem(driver=f"Closed trade {pid}", delta_risk=delta))
        trade_nodes.append(_trade_contributor(t0.portfolio, prev_by_id[pid], delta))
        running_positions, running_pf, running_risk = nxt_positions, nxt, risk_after

    for pid in common_ids:
        if not _position_changed(prev_by_id[pid], curr_by_id[pid]):
            continue
        nxt_positions = [curr_by_id[pid] if p.id == pid else p for p in running_positions]
        nxt = _clone_portfolio(t1.portfolio, nxt_positions, suffix=f"resize-{pid}")
        risk_after = value(nxt, t0.market)
        delta = risk_after - running_risk
        items.append(RiskChangeItem(driver=f"Position change {pid}", delta_risk=delta))
        trade_nodes.append(_trade_contributor(t1.portfolio, curr_by_id[pid], delta))
        running_positions, running_pf, running_risk = nxt_positions, nxt, risk_after

    for pid in new_ids:
        nxt_positions = [*running_positions, curr_by_id[pid]]
        nxt = _clone_portfolio(t1.portfolio, nxt_positions, suffix=f"new-{pid}")
        risk_after = value(nxt, t0.market)
        delta = risk_after - running_risk
        items.append(RiskChangeItem(driver=f"New trade {pid}", delta_risk=delta))
        trade_nodes.append(_trade_contributor(t1.portfolio, curr_by_id[pid], delta))
        running_positions, running_pf, running_risk = nxt_positions, nxt, risk_after

    # Unchanged continuing trades still appear in the hierarchy with ~0 delta
    # so drilldown can name every trade in the union of the two books.
    seen_ids = {n.position_id for n in trade_nodes}
    for pid in common_ids:
        if pid in seen_ids:
            continue
        trade_nodes.append(_trade_contributor(t1.portfolio, curr_by_id[pid], 0.0))

    after_trades = running_risk
    portfolio_trade_change = after_trades - computed_prev

    factor_contributors: list[RiskChangeFactorContributor] = []
    running_mkt = t0.market
    for factor in _changed_factors(t0.market, t1.market):
        nxt_mkt = _align_factor(running_mkt, t1.market, factor)
        risk_after = value(running_pf, nxt_mkt)
        delta = risk_after - running_risk
        factor_contributors.append(
            RiskChangeFactorContributor(
                factor_id=factor_column_id(factor),
                factor_type=factor.factor_type,
                factor=factor.key,
                bucket=factor.bucket,
                delta_risk=delta,
            )
        )
        items.append(RiskChangeItem(driver=factor_column_id(factor), delta_risk=delta))
        running_mkt, running_risk = nxt_mkt, risk_after

    market_change = running_risk - after_trades
    explained_change = portfolio_trade_change + market_change
    residual = total_change - explained_change
    items.append(RiskChangeItem(driver="residual / interactions", delta_risk=residual))

    identity = _identity_diff(t0, t1)
    disclosed = [name for name in identity.changed_fields if name in _DISCLOSE_FIELDS]
    if "historical_dataset_id" in disclosed or "historical_dataset_version" in disclosed:
        if "dataset" not in disclosed:
            disclosed.append("dataset")
    if "pricing_engine_version" in disclosed:
        disclosed.append("engine")
    if "calculation_config" in disclosed:
        disclosed.append("config")

    hierarchy = _hierarchy_tree(t1.portfolio if t1.portfolio.positions else t0.portfolio, trade_nodes)

    return RiskChangeReport(
        t0_run_id=t0.run.id,
        t1_run_id=t1.run.id,
        metric=metric_name,  # type: ignore[arg-type]
        unit=_unit(metric_name),
        sign_convention=_sign_convention(metric_name),
        previous_risk=previous_risk,
        current_risk=current_risk,
        total_change=total_change,
        portfolio_trade_change=portfolio_trade_change,
        market_change=market_change,
        explained_change=explained_change,
        residual=residual,
        identity=identity,
        disclosed_changes=disclosed,
        factor_contributors=factor_contributors,
        hierarchy_contributors=hierarchy,
        items=items,
    )
