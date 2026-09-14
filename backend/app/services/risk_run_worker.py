"""In-process / out-of-process risk-run execution (M5.4 / M5.7 / R0.3.5).

Uses a small ``ThreadPoolExecutor`` to **schedule risk-run jobs**, not to
parallelize QuantLib. That pool is not a distributed queue and must not call
``ql.Settings`` (or otherwise price QuantLib) except through
``PricingEngine.value`` → ``_session`` → ``_QL_PROCESS_LOCK``.

When ``QUANTLINEAGE_EXTERNAL_WORKER=1``, ``submit`` only enqueues QUEUED rows;
``poll_once`` (Compose ``worker`` / ``python -m app.worker``) drains them from
shared Postgres via ``claim_queued`` (Postgres: ``FOR UPDATE SKIP LOCKED``).
The Compose worker is a **separate OS process** with its own QuantLib globals.
Additional worker replicas are the supported parallel full-revaluation scale-out.
This module does not start a ``ProcessPoolExecutor`` or a job platform.
R0.6.5 keeps HEAVY full-reval on this worker process (Compose ``worker`` /
``QUANTLINEAGE_EXTERNAL_WORKER``); it does not add unused scenario-block
multiprocessing.
Redis/RQ is not required for safe multi-worker claim.

Lifecycle transitions go through ``RiskRunService``; persistence is either the
default in-memory repo or a SQLAlchemy session factory when provided.
"""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from app.api.acl import PortfolioAccessDenied, allow_read, allow_run_read
from app.api.errors import PUBLIC_RISK_RUN_FAILURE_MESSAGE
from app.api.scenario_wire import ScenarioWire, wires_to_scenarios
from app.api.schemas import RiskRunView, dump_risk_run_request, parse_risk_run_request
from app.domain.models import (
    AttributionRequest,
    MarketSnapshot,
    Portfolio,
    RiskChangeAttributionRequest,
    RiskChangeReport,
    RiskRun,
    RiskRunStatus,
    VaRMethodology,
)
from app.persistence.config import external_worker_enabled
from app.persistence.memory_repos import InMemoryMarketSnapshotRepository, InMemoryRiskRunRepository
from app.persistence.repositories import MarketSnapshotRepository, RiskRunRepository
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyMarketSnapshotRepository,
    SqlAlchemyPortfolioRepository,
    SqlAlchemyRiskRunRepository,
)
from app.risk.historical import HistoricalRiskEngine
from app.risk.risk_run_compare import BoundRiskRun, explain_risk_runs
from app.services.portfolio_service import PortfolioService
from app.services.risk_factories import (
    bind_pricing_engine,
    build_historical_risk_engine_for_spec,
    portfolio_service_for_spec,
    request_blob_for_execute,
    resolve_execute_spec,
    resolve_run_spec,
)
from app.services.risk_run_service import (
    InvalidRiskRunTransition,
    RiskRunNotFound,
    RiskRunService,
    elapsed_seconds,
)

logger = logging.getLogger(__name__)

SUPPORTED_RUN_TYPES = frozenset(
    {
        "summary",
        "var",
        "stress",
        "factors",
        "limits",
        "hierarchy",
        "contributors",
        "dashboard",
        "stress_evaluate",
        "reverse_stress",
        "reverse_stress_multi",
        "stress_compare",
        "query",
        "attribution",
        "attribution_demo",
        "change_attribution",
        "es",
        "var_compare",
    }
)


def _clone_snapshot(snapshot: MarketSnapshot) -> MarketSnapshot:
    """JSON round-trip copy so frozen mappingproxy maps stay pickle-safe."""
    return MarketSnapshot.model_validate(snapshot.model_dump(mode="json"))


def _serialize_result(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return {
            "items": [
                item.model_dump(mode="json") if isinstance(item, BaseModel) else item
                for item in value
            ]
        }
    if isinstance(value, dict):
        return value
    return {"value": value}


def _serialize_dashboard_result(batch: dict[str, Any]) -> dict[str, Any]:
    """JSON-ready dashboard batch: lists stay lists (not ``{"items": ...}``).

    Matches ``DashboardBatchResponse`` top-level keys for App.jsx / loadDashboard.
    """

    def _cell(value: Any) -> Any:
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if isinstance(value, list):
            return [
                item.model_dump(mode="json") if isinstance(item, BaseModel) else item
                for item in value
            ]
        return value

    return {key: _cell(value) for key, value in batch.items()}


def _parse_methodology(request: dict[str, Any]) -> VaRMethodology | None:
    raw = request.get("methodology")
    if raw is None or raw == "":
        return None
    if isinstance(raw, VaRMethodology):
        return raw
    return VaRMethodology(str(raw).strip().upper())


def _library_stress_scenarios(request: dict[str, Any]) -> list[Any] | None:
    """Optional named DEFAULT_SCENARIOS filter. None → full default library."""
    scenario_id = request.get("scenario_id")
    if not scenario_id:
        return None
    from app.risk.stress import DEFAULT_SCENARIOS

    selected = [item for item in DEFAULT_SCENARIOS if item.id == scenario_id]
    if not selected:
        raise ValueError(f"unknown stress scenario_id: {scenario_id}")
    return selected


def _scenarios_from_request(request: dict[str, Any]) -> list[Any]:
    raw = request.get("scenarios") or []
    return wires_to_scenarios([ScenarioWire.model_validate(item) for item in raw])


def execute_run_type(
    portfolio_service: PortfolioService,
    *,
    run_type: str,
    portfolio: Portfolio,
    request: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch to deterministic PortfolioService methods (no quant math here)."""
    if run_type not in SUPPORTED_RUN_TYPES:
        raise ValueError(
            f"unsupported run_type {run_type!r}; "
            f"supported: {sorted(SUPPORTED_RUN_TYPES)}"
        )
    methodology = _parse_methodology(request) or VaRMethodology.DELTA_GAMMA
    if run_type == "summary":
        return _serialize_result(
            portfolio_service.summary(portfolio, methodology=methodology)
        )
    if run_type == "var":
        return _serialize_result(
            portfolio_service.var_report(portfolio, methodology=methodology)
        )
    if run_type == "stress":
        return _serialize_result(
            portfolio_service.stresses(portfolio, _library_stress_scenarios(request))
        )
    if run_type == "factors":
        return _serialize_result(portfolio_service.factors(portfolio))
    if run_type == "limits":
        return _serialize_result(portfolio_service.limits(portfolio))
    if run_type == "hierarchy":
        return _serialize_result(portfolio_service.hierarchy(portfolio))
    if run_type == "contributors":
        return _serialize_result(portfolio_service.contributors(portfolio))
    if run_type == "dashboard":
        return _serialize_dashboard_result(portfolio_service.dashboard(portfolio))
    if run_type == "stress_evaluate":
        scenarios = _scenarios_from_request(request)
        return _serialize_result(
            portfolio_service.threat_evaluation(
                portfolio, scenarios if scenarios else None
            )
        )
    if run_type == "reverse_stress":
        target = request.get("target_loss_pct")
        if target is None:
            raise ValueError("reverse_stress requires target_loss_pct")
        factor = request.get("factor") or "equity"
        max_shock = request.get("max_shock", 0.80)
        return _serialize_result(
            portfolio_service.reverse_stress(
                portfolio, float(target), factor, float(max_shock)
            )
        )
    if run_type == "reverse_stress_multi":
        target = request.get("target_loss_pct")
        if target is None:
            raise ValueError("reverse_stress_multi requires target_loss_pct")
        return _serialize_result(
            portfolio_service.reverse_stress_multi(
                portfolio,
                float(target),
                factors=request.get("factors"),
                weights=request.get("weights"),
                max_shock=float(request.get("max_shock", 0.80)),
                max_shocks=request.get("max_shocks"),
            )
        )
    if run_type == "stress_compare":
        hedged = request.get("hedged_portfolio")
        if hedged is None:
            raise ValueError("stress_compare requires hedged_portfolio")
        hedged_book = (
            hedged if isinstance(hedged, Portfolio) else Portfolio.model_validate(hedged)
        )
        scenarios = _scenarios_from_request(request)
        if not scenarios:
            raise ValueError("stress_compare requires scenarios")
        return _serialize_result(
            portfolio_service.compare_scenarios(
                portfolio, hedged_book, scenarios, methodology=methodology
            )
        )
    if run_type == "query":
        question = request.get("question")
        if not question:
            raise ValueError("query requires question")
        return _serialize_result(portfolio_service.query(portfolio, str(question)))
    if run_type == "attribution":
        attr_req = AttributionRequest.model_validate(
            {
                "previous_portfolio": request.get("previous_portfolio") or portfolio,
                "current_portfolio": request.get("current_portfolio") or portfolio,
                "previous_market": request.get("previous_market"),
                "current_market": request.get("current_market"),
                "dt_years": request.get("dt_years", 0.0),
            }
        )
        return _serialize_result(portfolio_service.attribution(attr_req))
    if run_type == "attribution_demo":
        return _serialize_result(portfolio_service.demo_attribution(portfolio))
    if run_type == "change_attribution":
        change_req = RiskChangeAttributionRequest.model_validate(
            {
                "previous_portfolio": request.get("previous_portfolio") or portfolio,
                "current_portfolio": request.get("current_portfolio") or portfolio,
                "previous_market": request.get("previous_market"),
                "current_market": request.get("current_market"),
                "metric": request.get("metric") or "var_99",
                "methodology": methodology,
            }
        )
        return _serialize_result(portfolio_service.risk_change_attribution(change_req))
    if run_type == "es":
        return _serialize_result(
            portfolio_service.es_contributions(portfolio, methodology=methodology)
        )
    if run_type == "var_compare":
        observations = request.get("observations")
        return _serialize_result(
            portfolio_service.compare_var_methodologies(
                portfolio,
                observations=int(observations) if observations is not None else None,
            )
        )
    raise ValueError(f"unsupported run_type {run_type!r}")


class RiskRunWorker:
    """Enqueue risk runs and execute them on a background thread pool."""

    def __init__(
        self,
        portfolio_service: PortfolioService,
        *,
        repo: RiskRunRepository | None = None,
        session_factory: Any | None = None,
        max_workers: int = 2,
        market_snapshots: MarketSnapshotRepository | None = None,
    ) -> None:
        if repo is not None and session_factory is not None:
            raise ValueError("provide either repo or session_factory, not both")
        self._portfolio_service = portfolio_service
        self._session_factory = session_factory
        self._memory_repo = repo
        if session_factory is None and self._memory_repo is None:
            self._memory_repo = InMemoryRiskRunRepository()
        if session_factory is None and market_snapshots is None:
            self._market_snapshots = InMemoryMarketSnapshotRepository()
        else:
            self._market_snapshots = market_snapshots
        self._max_workers = max_workers
        self._portfolios: dict[str, Portfolio] = {}
        self._completed_portfolios: dict[str, Portfolio] = {}
        self._completed_markets: dict[str, MarketSnapshot] = {}
        self._portfolios_lock = threading.Lock()
        self._executor_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="risk-run",
        )
        self._futures: dict[str, Future[None]] = {}
        self._futures_lock = threading.Lock()

    def ensure_running(self) -> None:
        """Recreate the pool if a prior lifespan shut it down (TestClient)."""
        with self._executor_lock:
            if getattr(self._executor, "_shutdown", False):
                self._executor = ThreadPoolExecutor(
                    max_workers=self._max_workers,
                    thread_name_prefix="risk-run",
                )

    def _with_service(self, fn: Callable[[RiskRunService], Any]) -> Any:
        if self._session_factory is not None:
            with session_scope(self._session_factory) as session:
                return fn(RiskRunService(SqlAlchemyRiskRunRepository(session)))
        assert self._memory_repo is not None
        return fn(RiskRunService(self._memory_repo))

    def _list_by_status(self, status: RiskRunStatus, *, limit: int) -> list[RiskRun]:
        if self._session_factory is not None:
            with session_scope(self._session_factory) as session:
                return SqlAlchemyRiskRunRepository(session).list_by_status(
                    status, limit=limit
                )
        assert self._memory_repo is not None
        return self._memory_repo.list_by_status(status, limit=limit)

    def _claim_queued(self, *, limit: int) -> list[RiskRun]:
        """Atomically claim QUEUED → RUNNING (Postgres: SKIP LOCKED)."""
        if self._session_factory is not None:
            with session_scope(self._session_factory) as session:
                return SqlAlchemyRiskRunRepository(session).claim_queued(limit=limit)
        assert self._memory_repo is not None
        return self._memory_repo.claim_queued(limit=limit)

    def _load_market_snapshot(self, snapshot_id: str) -> MarketSnapshot | None:
        if self._session_factory is not None:
            with session_scope(self._session_factory) as session:
                return SqlAlchemyMarketSnapshotRepository(session).get(snapshot_id)
        if self._market_snapshots is not None:
            return self._market_snapshots.get(snapshot_id)
        return None

    def _persist_execute_market(self, market: MarketSnapshot) -> None:
        """Save the execute-time snapshot if the repo does not already have it."""
        if self._session_factory is not None:
            with session_scope(self._session_factory) as session:
                repo = SqlAlchemyMarketSnapshotRepository(session)
                if repo.get(market.id) is None:
                    repo.save(market)
            return
        if self._market_snapshots is not None and self._market_snapshots.get(market.id) is None:
            self._market_snapshots.save(market)

    def _stamp_execute_market(self, run_id: str, market: MarketSnapshot) -> None:
        self._persist_execute_market(market)
        self._with_service(lambda svc: svc.bind_market_snapshot(run_id, market.id))

    def _load_portfolio(self, portfolio_id: str) -> Portfolio | None:
        if self._session_factory is None:
            return None
        with session_scope(self._session_factory) as session:
            return SqlAlchemyPortfolioRepository(session).get(portfolio_id)

    def _book_for_run(self, portfolio: Portfolio, *, principal: str | None) -> Portfolio:
        """Create-if-absent; attach the stored book when the id already exists."""
        if self._session_factory is None:
            return portfolio
        with session_scope(self._session_factory) as session:
            repo = SqlAlchemyPortfolioRepository(session)
            stored = repo.get(portfolio.id)
            if stored is not None:
                owner = repo.get_owner(portfolio.id)
                if not allow_read(owner, principal):
                    raise PortfolioAccessDenied(portfolio.id)
                return stored
            return repo.create(portfolio, owner=principal)

    def _to_view(self, run: RiskRun) -> RiskRunView:
        payloads = self._with_service(lambda svc: svc.get_result_payloads(run.id))
        view = RiskRunView.from_risk_run(run, payloads=payloads or {})
        # Live duration while RUNNING (domain ``duration`` only for terminal states).
        if view.duration_seconds is None:
            live = elapsed_seconds(run)
            if live is not None:
                updates: dict[str, Any] = {"duration_seconds": live}
                if view.provenance is not None:
                    updates["provenance"] = view.provenance.model_copy(
                        update={"duration_seconds": live}
                    )
                view = view.model_copy(update=updates)
        return view

    def _schedule(self, run_id: str) -> None:
        self.ensure_running()
        with self._futures_lock:
            existing = self._futures.get(run_id)
            if existing is not None and not existing.done():
                return
        with self._executor_lock:
            future = self._executor.submit(self._execute, run_id)
        with self._futures_lock:
            self._futures[run_id] = future

    def submit(
        self,
        *,
        portfolio: Portfolio,
        run_type: str = "summary",
        request: dict[str, Any] | None = None,
        market_snapshot_id: str | None = None,
        run_id: str | None = None,
        execute: bool | None = None,
        owner: str | None = None,
    ) -> RiskRunView:
        """Create a QUEUED run; optionally schedule background execution.

        ``execute=None`` follows ``QUANTLINEAGE_EXTERNAL_WORKER`` (Compose backend
        defers to the ``worker`` service). Explicit ``execute=True/False``
        overrides the env flag (tests).
        """
        self.ensure_running()
        run_type = (run_type or "summary").strip()
        if run_type not in SUPPORTED_RUN_TYPES:
            raise ValueError(
                f"unsupported run_type {run_type!r}; "
                f"supported: {sorted(SUPPORTED_RUN_TYPES)}"
            )
        rid = run_id or str(uuid.uuid4())
        try:
            typed_request = parse_risk_run_request(run_type, request)
        except ValidationError as exc:
            raise ValueError(f"invalid risk run request: {exc}") from exc
        req = dump_risk_run_request(typed_request)
        methodology = _parse_methodology(req)
        engine = getattr(self._portfolio_service, "risk", None)
        try:
            spec = resolve_run_spec(
                typed_request,
                risk_engine=engine if isinstance(engine, HistoricalRiskEngine) else None,
                run_type=run_type,
            )
        except ValueError:
            raise
        except ValidationError as exc:
            raise ValueError(f"invalid risk run request: {exc}") from exc

        book = self._book_for_run(portfolio, principal=owner)

        def _enqueue(svc: RiskRunService) -> RiskRun:
            return svc.enqueue(
                run_id=rid,
                portfolio_id=book.id,
                portfolio_version=book.version,
                owner=owner,
                run_type=run_type,
                request=req,
                market_snapshot_id=market_snapshot_id,
                methodology=methodology,
                historical_dataset_id=spec.historical_dataset_id,
                historical_dataset_version=spec.historical_dataset_version,
                as_of=spec.as_of,
                calculation_config=spec.calculation_config,
            )

        run = self._with_service(_enqueue)
        with self._portfolios_lock:
            self._portfolios[rid] = book.model_copy(deep=True)
            self._completed_portfolios[rid] = book.model_copy(deep=True)

        should_execute = (not external_worker_enabled()) if execute is None else bool(execute)
        if should_execute:
            self._schedule(rid)
        return RiskRunView.from_risk_run(run)

    def get(self, run_id: str, *, principal: str | None = None) -> RiskRunView:
        run = self._with_service(lambda svc: svc.get(run_id))
        if not allow_run_read(run.owner, principal):
            raise PortfolioAccessDenied(run.portfolio_id)
        return self._to_view(run)

    def _bound_portfolio(self, run: RiskRun) -> Portfolio:
        with self._portfolios_lock:
            book = self._completed_portfolios.get(run.id) or self._portfolios.get(run.id)
        if book is not None:
            return book.model_copy(deep=True)
        loaded = self._load_portfolio(run.portfolio_id)
        if loaded is None:
            raise ValueError(f"portfolio payload missing for completed run {run.id}")
        if run.portfolio_version is None or loaded.version != run.portfolio_version:
            raise ValueError(
                f"cannot bind run {run.id}: live book version {loaded.version!r} "
                f"does not match run portfolio_version {run.portfolio_version!r}"
            )
        return loaded

    def _bound_market(self, run: RiskRun, portfolio: Portfolio) -> MarketSnapshot:
        with self._portfolios_lock:
            cached = self._completed_markets.get(run.id)
        if cached is not None:
            if run.market_snapshot_id and cached.id != run.market_snapshot_id:
                raise ValueError(
                    f"cannot bind run {run.id}: cached market {cached.id!r} "
                    f"does not match run market_snapshot_id {run.market_snapshot_id!r}"
                )
            return _clone_snapshot(cached)
        if run.market_snapshot_id:
            market = self._load_market_snapshot(run.market_snapshot_id)
            if market is None:
                raise ValueError(f"market snapshot {run.market_snapshot_id!r} not found")
            return market
        raise ValueError(
            f"cannot bind run {run.id}: market snapshot missing "
            "(no execute-time cache and no market_snapshot_id)"
        )

    @staticmethod
    def _persisted_metrics(
        payloads: dict[str, dict[str, Any]] | None,
        *,
        scenario_set: list[str] | None = None,
    ) -> dict[str, float]:
        out: dict[str, float] = {}
        if not payloads:
            return out
        wanted = list(scenario_set or [])
        for payload in payloads.values():
            if not isinstance(payload, dict):
                continue
            for key in ("var_99", "var_95", "expected_shortfall_99", "dv01", "vega"):
                raw = payload.get(key)
                if isinstance(raw, int | float):
                    out[key] = float(raw)
            items = payload.get("items")
            if not isinstance(items, list) or not items:
                continue
            chosen = None
            if wanted:
                from app.risk.stress import DEFAULT_SCENARIOS, THREAT_SCENARIOS

                labels = set(wanted)
                for defn in (*DEFAULT_SCENARIOS, *THREAT_SCENARIOS):
                    if defn.id in wanted:
                        labels.add(defn.name)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    label = item.get("scenario") or item.get("id") or item.get("scenario_id")
                    if label in labels:
                        chosen = item
                        break
            elif isinstance(items[0], dict):
                chosen = items[0]
            if chosen is not None and isinstance(chosen.get("pnl"), int | float):
                out.setdefault("stress", float(chosen["pnl"]))
        return out

    def compare_runs(
        self,
        t0_run_id: str,
        t1_run_id: str,
        *,
        metric: str = "var_99",
        principal: str | None = None,
    ) -> RiskChangeReport:
        t0 = self._with_service(lambda svc: svc.get(t0_run_id))
        t1 = self._with_service(lambda svc: svc.get(t1_run_id))
        if not allow_run_read(t0.owner, principal):
            raise PortfolioAccessDenied(t0.portfolio_id)
        if not allow_run_read(t1.owner, principal):
            raise PortfolioAccessDenied(t1.portfolio_id)
        if t0.status != RiskRunStatus.COMPLETED or t1.status != RiskRunStatus.COMPLETED:
            raise ValueError("both RiskRuns must be COMPLETED")
        p0 = self._bound_portfolio(t0)
        p1 = self._bound_portfolio(t1)
        m0 = self._bound_market(t0, p0)
        m1 = self._bound_market(t1, p1)
        payloads0 = self._with_service(lambda svc: svc.get_result_payloads(t0.id))
        payloads1 = self._with_service(lambda svc: svc.get_result_payloads(t1.id))
        spec0 = resolve_execute_spec(t0)
        spec1 = resolve_execute_spec(t1)
        engine_t0 = build_historical_risk_engine_for_spec(spec0)
        engine_t1: HistoricalRiskEngine | None = None
        if (
            spec0.historical_dataset_id != spec1.historical_dataset_id
            or spec0.historical_dataset_version != spec1.historical_dataset_version
            or spec0.calculation_config != spec1.calculation_config
        ):
            engine_t1 = build_historical_risk_engine_for_spec(spec1)
        pricing = bind_pricing_engine(
            t0.pricing_engine_version,
            fallback=self._portfolio_service.pricing,
        )
        t1_pricing = None
        if t0.pricing_engine_version != t1.pricing_engine_version:
            t1_pricing = bind_pricing_engine(
                t1.pricing_engine_version,
                fallback=self._portfolio_service.pricing,
            )
        return explain_risk_runs(
            BoundRiskRun(
                run=t0,
                portfolio=p0,
                market=m0,
                persisted_metrics=self._persisted_metrics(
                    payloads0, scenario_set=list(t0.scenario_set)
                ),
            ),
            BoundRiskRun(
                run=t1,
                portfolio=p1,
                market=m1,
                persisted_metrics=self._persisted_metrics(
                    payloads1, scenario_set=list(t1.scenario_set)
                ),
            ),
            metric=metric,
            pricing=pricing,
            risk_engine=engine_t0,
            t1_risk_engine=engine_t1,
            t1_pricing=t1_pricing,
        )

    def poll_once(self, *, limit: int = 10) -> int:
        """Claim up to ``limit`` QUEUED runs and schedule execution.

        Uses ``claim_queued`` (Postgres ``FOR UPDATE SKIP LOCKED``) so two
        workers cannot own the same row. Loads portfolios from SQLAlchemy when
        the in-memory cache misses. Returns how many runs were newly scheduled.
        """
        claimed = self._claim_queued(limit=limit)
        scheduled = 0
        for run in claimed:
            with self._portfolios_lock:
                portfolio = self._portfolios.get(run.id)
            if portfolio is None:
                portfolio = self._load_portfolio(run.portfolio_id)
                if portfolio is None:
                    self._with_service(
                        lambda svc, rid=run.id, pid=run.portfolio_id: svc.fail(
                            rid, f"portfolio {pid!r} missing for queued run"
                        )
                    )
                    continue
                with self._portfolios_lock:
                    self._portfolios[run.id] = portfolio.model_copy(deep=True)
                    self._completed_portfolios[run.id] = portfolio.model_copy(deep=True)
            with self._futures_lock:
                existing = self._futures.get(run.id)
                if existing is not None and not existing.done():
                    continue
            self._schedule(run.id)
            scheduled += 1
        return scheduled

    def _execute(self, run_id: str) -> None:
        try:
            header = self._with_service(lambda svc: svc.get(run_id))
            if header.status == RiskRunStatus.QUEUED:
                # In-process submit path: claim/start here.
                try:
                    self._with_service(lambda svc: svc.start(run_id))
                except InvalidRiskRunTransition:
                    # Race with another executor; do not fail the run.
                    logger.info("skip run already claimed: %s", run_id)
                    return
            elif header.status == RiskRunStatus.RUNNING:
                # Already claimed by poll_once / claim_queued (out-of-process).
                pass
            else:
                # Terminal or unexpected — another worker finished this run.
                return
            with self._portfolios_lock:
                portfolio = self._portfolios.get(run_id)
            if portfolio is None:
                portfolio = self._load_portfolio(header.portfolio_id)
            if portfolio is None:
                self._with_service(
                    lambda svc: svc.fail(run_id, "portfolio payload missing for run")
                )
                return
            header = self._with_service(lambda svc: svc.get(run_id))
            # Prefer first-class persisted columns over the request blob (R0.8.5).
            req = request_blob_for_execute(header)
            engine = getattr(self._portfolio_service, "risk", None)
            spec = resolve_execute_spec(
                header,
                risk_engine=engine if isinstance(engine, HistoricalRiskEngine) else None,
            )
            market = None
            if header.market_snapshot_id:
                market = self._load_market_snapshot(header.market_snapshot_id)
                if market is None:
                    self._with_service(
                        lambda svc: svc.fail(
                            run_id,
                            f"market snapshot {header.market_snapshot_id!r} not found",
                        )
                    )
                    return
            else:
                market = self._portfolio_service.market_snapshot(portfolio)
                self._stamp_execute_market(run_id, market)
            with self._portfolios_lock:
                self._completed_portfolios[run_id] = portfolio.model_copy(deep=True)
                self._completed_markets[run_id] = _clone_snapshot(market)
            run_service = portfolio_service_for_spec(
                self._portfolio_service, spec, market=market
            )
            payload = execute_run_type(
                run_service,
                run_type=header.run_type,
                portfolio=portfolio,
                request=req,
            )
            self._with_service(
                lambda svc: svc.complete(
                    run_id,
                    result_type=header.run_type,
                    payload=payload,
                )
            )
        except RiskRunNotFound:
            logger.exception("risk run disappeared during execution: %s", run_id)
        except Exception:  # noqa: BLE001 — surface as FAILED status
            logger.exception("risk run failed: %s", run_id)
            try:
                self._with_service(
                    lambda svc: svc.fail(run_id, PUBLIC_RISK_RUN_FAILURE_MESSAGE)
                )
            except Exception:  # noqa: BLE001
                logger.exception("could not mark risk run FAILED: %s", run_id)
        finally:
            with self._portfolios_lock:
                self._portfolios.pop(run_id, None)
            with self._futures_lock:
                self._futures.pop(run_id, None)

    def shutdown(self, *, wait: bool = False) -> None:
        with self._executor_lock:
            self._executor.shutdown(wait=wait)
