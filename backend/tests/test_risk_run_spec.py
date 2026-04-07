"""R0.8.1 persistence + R0.8.2 enqueue/submit spec population.

Does not close RF-009 (server-owned identity and typed request schemas remain).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from app.domain.models import (
    EquityPosition,
    MarketSnapshot,
    Portfolio,
    RiskRun,
    RiskRunCalculationConfig,
    RiskRunStatus,
    RiskRunView,
    VaRMethodology,
)
from app.persistence.memory_repos import InMemoryRiskRunRepository
from app.persistence.models import RiskRunRow
from app.persistence.risk_run_mapping import risk_run_to_row, row_to_risk_run
from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyMarketSnapshotRepository,
    SqlAlchemyPortfolioRepository,
    SqlAlchemyRiskRunRepository,
)
from app.persistence.testing import make_sqlite_session_factory
from app.services.risk_factories import (
    DEFAULT_HISTORICAL_DATASET_VERSION,
    build_portfolio_service,
    resolve_run_spec,
)
from app.services.risk_run_service import RiskRunService
from app.services.risk_run_worker import RiskRunWorker


def _ts() -> datetime:
    return datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def _full_spec_run() -> RiskRun:
    return RiskRun(
        id="run-spec",
        portfolio_id="p-spec",
        market_snapshot_id="snap-spec",
        created_at=_ts(),
        pricing_engine_version="builtin-1.0",
        methodology=VaRMethodology.DELTA_GAMMA,
        scenario_set=["base", "eq-crash"],
        historical_dataset_id="demo-historical-factors",
        historical_dataset_version="v1",
        as_of=date(2026, 9, 2),
        calculation_config=RiskRunCalculationConfig(
            observations=750,
            seed=7,
            confidence=0.99,
        ),
    )


def test_risk_run_constructs_with_all_spec_fields():
    run = _full_spec_run()
    assert run.historical_dataset_id == "demo-historical-factors"
    assert run.historical_dataset_version == "v1"
    assert run.as_of == date(2026, 9, 2)
    assert run.calculation_config is not None
    assert run.calculation_config.observations == 750
    assert run.calculation_config.seed == 7
    assert run.calculation_config.confidence == pytest.approx(0.99)


def test_risk_run_omitted_spec_fields_remain_valid():
    run = RiskRun(id="run-old", portfolio_id="p-old")
    assert run.historical_dataset_id is None
    assert run.historical_dataset_version is None
    assert run.as_of is None
    assert run.calculation_config is None


@pytest.mark.parametrize("as_of", ["current", "t0", date(2026, 1, 15), "2026-01-15"])
def test_risk_run_as_of_reuses_snapshot_type(as_of):
    run = RiskRun(id="run-asof", portfolio_id="p-1", as_of=as_of)
    if as_of in {"current", "t0"}:
        assert run.as_of == as_of
    else:
        assert run.as_of == date(2026, 1, 15)


def test_risk_run_as_of_rejects_unparseable():
    with pytest.raises(ValidationError):
        RiskRun(id="run-asof", portfolio_id="p-1", as_of="later")


def test_calculation_config_rejects_unknown_keys():
    with pytest.raises(ValidationError):
        RiskRunCalculationConfig(observations=10, api_key="secret")


def test_mapping_round_trip_preserves_spec_fields():
    run = _full_spec_run()
    row = risk_run_to_row(run)
    assert row.historical_dataset_id == "demo-historical-factors"
    assert row.historical_dataset_version == "v1"
    assert row.as_of == "2026-09-02"
    assert row.calculation_config == {
        "observations": 750,
        "seed": 7,
        "confidence": 0.99,
    }

    back = row_to_risk_run(row)
    assert back.model_dump() == run.model_dump()


def test_mapping_old_row_without_spec_fields_loads():
    row = RiskRunRow(
        id="run-legacy",
        portfolio_id="p-legacy",
        status=RiskRunStatus.QUEUED,
        run_type="summary",
        request={},
        scenario_set=[],
        created_at=_ts(),
    )
    loaded = row_to_risk_run(row)
    assert loaded.historical_dataset_id is None
    assert loaded.historical_dataset_version is None
    assert loaded.as_of is None
    assert loaded.calculation_config is None
    assert loaded.portfolio_id == "p-legacy"
    assert loaded.status == RiskRunStatus.QUEUED


def test_sqlite_persist_reload_equals_full_spec():
    portfolio = Portfolio(
        id="p-spec",
        name="Spec Book",
        positions=[
            EquityPosition(type="equity", id="eq-1", symbol="AAPL", quantity=1, price=100.0)
        ],
    )
    snap = MarketSnapshot(id="snap-spec", equity_spots={"AAPL": 100.0})
    queued = _full_spec_run()
    factory = make_sqlite_session_factory()
    with session_scope(factory) as session:
        SqlAlchemyPortfolioRepository(session).save(portfolio)
        SqlAlchemyMarketSnapshotRepository(session).save(snap)
        stored = SqlAlchemyRiskRunRepository(session).create(queued)
        assert stored.model_dump() == queued.model_dump()

    with session_scope(factory) as session:
        loaded = SqlAlchemyRiskRunRepository(session).get("run-spec")
        assert loaded is not None
        assert loaded.model_dump() == queued.model_dump()


def test_sqlite_old_run_without_spec_fields_still_loads():
    portfolio = Portfolio(
        id="p-old",
        name="Old Book",
        positions=[
            EquityPosition(type="equity", id="eq-1", symbol="AAPL", quantity=1, price=100.0)
        ],
    )
    factory = make_sqlite_session_factory()
    with session_scope(factory) as session:
        SqlAlchemyPortfolioRepository(session).save(portfolio)
        SqlAlchemyRiskRunRepository(session).create(
            RiskRun(id="run-old", portfolio_id="p-old")
        )

    with session_scope(factory) as session:
        loaded = SqlAlchemyRiskRunRepository(session).get("run-old")
        assert loaded is not None
        assert loaded.historical_dataset_id is None
        assert loaded.historical_dataset_version is None
        assert loaded.as_of is None
        assert loaded.calculation_config is None


def test_memory_persist_reload_equals_full_spec():
    repo = InMemoryRiskRunRepository()
    queued = _full_spec_run()
    stored = repo.create(queued)
    assert stored.model_dump() == queued.model_dump()
    loaded = repo.get("run-spec")
    assert loaded is not None
    assert loaded.model_dump() == queued.model_dump()


def test_memory_set_status_preserves_spec_fields():
    repo = InMemoryRiskRunRepository()
    repo.create(_full_spec_run())
    running = repo.set_status("run-spec", RiskRunStatus.RUNNING)
    assert running.historical_dataset_id == "demo-historical-factors"
    assert running.historical_dataset_version == "v1"
    assert running.as_of == date(2026, 9, 2)
    assert running.calculation_config is not None
    assert running.calculation_config.observations == 750


def test_risk_run_view_exposes_spec_fields():
    view = RiskRunView.from_risk_run(_full_spec_run())
    assert view.historical_dataset_id == "demo-historical-factors"
    assert view.historical_dataset_version == "v1"
    assert view.as_of == "2026-09-02"
    assert view.calculation_config is not None
    assert view.calculation_config.observations == 750


def _tiny_book() -> Portfolio:
    return Portfolio(
        id="p-enqueue",
        name="Enqueue Book",
        positions=[
            EquityPosition(type="equity", id="eq-1", symbol="AAPL", quantity=1, price=100.0)
        ],
    )


def test_enqueue_persists_explicit_spec_fields():
    repo = InMemoryRiskRunRepository()
    svc = RiskRunService(repo)
    run = svc.enqueue(
        run_id="enq-spec",
        portfolio_id="p-enqueue",
        historical_dataset_id="demo-historical-factors",
        historical_dataset_version="v1",
        as_of=date(2026, 9, 2),
        calculation_config=RiskRunCalculationConfig(
            observations=750,
            seed=7,
            confidence=0.99,
        ),
    )
    assert run.historical_dataset_id == "demo-historical-factors"
    assert run.historical_dataset_version == "v1"
    assert run.as_of == date(2026, 9, 2)
    assert run.calculation_config is not None
    assert run.calculation_config.confidence == pytest.approx(0.99)

    loaded = repo.get("enq-spec")
    assert loaded is not None
    assert loaded.model_dump() == run.model_dump()


def test_enqueue_without_spec_kwargs_stays_valid():
    repo = InMemoryRiskRunRepository()
    svc = RiskRunService(repo)
    run = svc.enqueue(run_id="enq-old", portfolio_id="p-enqueue")
    assert run.status == RiskRunStatus.QUEUED
    assert run.historical_dataset_id is None
    assert run.historical_dataset_version is None
    assert run.as_of is None
    assert run.calculation_config is None


def test_submit_with_request_spec_persists_columns():
    repo = InMemoryRiskRunRepository()
    worker = RiskRunWorker(build_portfolio_service(), repo=repo, max_workers=1)
    view = worker.submit(
        portfolio=_tiny_book(),
        run_type="summary",
        execute=False,
        request={
            "methodology": "DELTA_GAMMA",
            "historical_dataset_id": "demo-historical-factors",
            "historical_dataset_version": "v1",
            "as_of": "2026-09-02",
            "calculation_config": {
                "observations": 750,
                "seed": 7,
                "confidence": 0.99,
            },
        },
    )
    worker.shutdown(wait=False)
    assert view.historical_dataset_id == "demo-historical-factors"
    assert view.historical_dataset_version == "v1"
    assert view.as_of == "2026-09-02"
    assert view.calculation_config is not None
    assert view.calculation_config.observations == 750
    assert view.calculation_config.seed == 7
    assert view.calculation_config.confidence == pytest.approx(0.99)

    stored = repo.get(view.id)
    assert stored is not None
    assert stored.historical_dataset_id == "demo-historical-factors"
    assert stored.historical_dataset_version == "v1"
    assert stored.as_of == date(2026, 9, 2)
    assert stored.calculation_config is not None
    assert stored.calculation_config.confidence == pytest.approx(0.99)


@pytest.mark.parametrize("as_of", ["current", "t0", "2026-01-15"])
def test_submit_parses_as_of_from_request(as_of: str):
    repo = InMemoryRiskRunRepository()
    worker = RiskRunWorker(build_portfolio_service(), repo=repo, max_workers=1)
    view = worker.submit(
        portfolio=_tiny_book(),
        execute=False,
        request={"as_of": as_of},
    )
    worker.shutdown(wait=False)
    stored = repo.get(view.id)
    assert stored is not None
    if as_of in {"current", "t0"}:
        assert stored.as_of == as_of
        assert view.as_of == as_of
    else:
        assert stored.as_of == date(2026, 1, 15)
        assert view.as_of == "2026-01-15"


def test_submit_without_request_spec_records_factory_dataset():
    repo = InMemoryRiskRunRepository()
    service = build_portfolio_service()
    factory_spec = resolve_run_spec(risk_engine=service.risk)
    worker = RiskRunWorker(service, repo=repo, max_workers=1)
    view = worker.submit(portfolio=_tiny_book(), run_type="summary", execute=False)
    worker.shutdown(wait=False)

    assert view.historical_dataset_id == factory_spec.historical_dataset_id
    assert view.historical_dataset_version == factory_spec.historical_dataset_version
    assert view.historical_dataset_id is not None
    assert view.historical_dataset_version == DEFAULT_HISTORICAL_DATASET_VERSION

    stored = repo.get(view.id)
    assert stored is not None
    populated = [
        stored.historical_dataset_id,
        stored.historical_dataset_version,
        stored.as_of,
        stored.calculation_config,
    ]
    assert any(value is not None for value in populated)
    assert stored.historical_dataset_id == factory_spec.historical_dataset_id
    assert stored.calculation_config is not None
    assert factory_spec.calculation_config is not None
    assert stored.calculation_config.observations == factory_spec.calculation_config.observations
    assert stored.calculation_config.seed == factory_spec.calculation_config.seed


def test_submit_unparseable_as_of_does_not_fail_enqueue():
    repo = InMemoryRiskRunRepository()
    worker = RiskRunWorker(build_portfolio_service(), repo=repo, max_workers=1)
    view = worker.submit(
        portfolio=_tiny_book(),
        execute=False,
        request={"as_of": "later"},
    )
    worker.shutdown(wait=False)
    stored = repo.get(view.id)
    assert stored is not None
    assert stored.as_of is None
    assert stored.historical_dataset_id is not None
