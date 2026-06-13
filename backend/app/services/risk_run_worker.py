"""In-process / out-of-process risk-run execution (M5.4 / M5.7 / R0.3.5).

Uses a small ``ThreadPoolExecutor`` to **schedule risk-run jobs**, not to
parallelize QuantLib. That pool is not a distributed queue and must not call
``ql.Settings`` (or otherwise price QuantLib) except through
``PricingEngine.value`` → ``_session`` → ``_QL_PROCESS_LOCK``.

When ``RISKFORGE_EXTERNAL_WORKER=1``, ``submit`` only enqueues QUEUED rows;
``poll_once`` (Compose ``worker`` / ``python -m app.worker``) drains them from
shared Postgres via ``claim_queued`` (Postgres: ``FOR UPDATE SKIP LOCKED``).
The Compose worker is a **separate OS process** with its own QuantLib globals.
Additional worker replicas are the supported parallel full-revaluation scale-out.
This module does not start a ``ProcessPoolExecutor`` or a job platform.
R0.6.5 keeps HEAVY full-reval on this worker process (Compose ``worker`` /
``RISKFORGE_EXTERNAL_WORKER``); it does not add unused scenario-block
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

from app.api.errors import PUBLIC_RISK_RUN_FAILURE_MESSAGE
from app.api.scenario_wire import ScenarioWire, wires_to_scenarios
from app.api.schemas import RiskRunView, dump_risk_run_request, parse_risk_run_request
from app.domain.models import (
    AttributionRequest,
    Portfolio,
    RiskChangeAttributionRequest,
    RiskRun,
    RiskRunStatus,
    VaRMethodology,
)
from app.persistence.config import external_worker_enabled
from app.persistence.memory_repos import InMemoryRiskRunRepository
from app.persistence.repositories import RiskRunRepository
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyPortfolioRepository,
    SqlAlchemyRiskRunRepository,
)
from app.risk.historical import HistoricalRiskEngine
from app.services.portfolio_service import PortfolioService
from app.services.risk_factories import (
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
        return _serialize_result(portfolio_service.stresses(portfolio))
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
    ) -> None:
        if repo is not None and session_factory is not None:
            raise ValueError("provide either repo or session_factory, not both")
        self._portfolio_service = portfolio_service
        self._session_factory = session_factory
        self._memory_repo = repo
        if session_factory is None and self._memory_repo is None:
            self._memory_repo = InMemoryRiskRunRepository()
        self._max_workers = max_workers
        self._portfolios: dict[str, Portfolio] = {}
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

    def _load_portfolio(self, portfolio_id: str) -> Portfolio | None:
        if self._session_factory is None:
            return None
        with session_scope(self._session_factory) as session:
            return SqlAlchemyPortfolioRepository(session).get(portfolio_id)

    def _book_for_run(self, portfolio: Portfolio) -> Portfolio:
        """Create-if-absent; attach the stored book when the id already exists."""
        if self._session_factory is None:
            return portfolio
        with session_scope(self._session_factory) as session:
            repo = SqlAlchemyPortfolioRepository(session)
            stored = repo.get(portfolio.id)
            if stored is not None:
                return stored
            return repo.create(portfolio)

    def _to_view(self, run: RiskRun) -> RiskRunView:
        payloads = self._with_service(lambda svc: svc.get_result_payloads(run.id))
        view = RiskRunView.from_risk_run(run, payloads=payloads or {})
        # Live duration while RUNNING (domain ``duration`` only for terminal states).
        if view.duration_seconds is None:
            live = elapsed_seconds(run)
            if live is not None:
                view = view.model_copy(update={"duration_seconds": live})
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
    ) -> RiskRunView:
        """Create a QUEUED run; optionally schedule background execution.

        ``execute=None`` follows ``RISKFORGE_EXTERNAL_WORKER`` (Compose backend
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

        book = self._book_for_run(portfolio)

        def _enqueue(svc: RiskRunService) -> RiskRun:
            return svc.enqueue(
                run_id=rid,
                portfolio_id=book.id,
                portfolio_version=book.version,
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

        should_execute = (not external_worker_enabled()) if execute is None else bool(execute)
        if should_execute:
            self._schedule(rid)
        return RiskRunView.from_risk_run(run)

    def get(self, run_id: str) -> RiskRunView:
        run = self._with_service(lambda svc: svc.get(run_id))
        return self._to_view(run)

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
            run_service = portfolio_service_for_spec(self._portfolio_service, spec)
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
