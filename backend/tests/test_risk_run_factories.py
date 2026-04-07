"""R0.8.2: API and worker share one pricing + historical-dataset factory.

Does not close RF-009 (persistence identity and typed request schemas remain).
"""

from __future__ import annotations

import inspect

import pytest

from app.risk.historical import HistoricalRiskEngine
from app.risk.historical_data import (
    DEMO_HISTORICAL_DATASET_ID,
    FileHistoricalDataset,
    SyntheticHistoricalDataset,
    create_historical_dataset,
)
from app.services.risk_factories import (
    DEFAULT_HISTORICAL_DATASET_VERSION,
    SYNTHETIC_HISTORICAL_DATASET_ID,
    build_portfolio_service,
    resolve_run_spec,
)


def test_deps_and_worker_use_same_factory_callable():
    import app.api.deps as deps
    import app.worker as worker

    assert deps.build_portfolio_service is build_portfolio_service
    assert worker.build_portfolio_service is build_portfolio_service


def test_worker_main_constructs_via_shared_factory():
    import app.worker as worker

    source = inspect.getsource(worker.main)
    assert "build_portfolio_service" in source
    assert "HistoricalRiskEngine()" not in source


def test_build_portfolio_service_wires_create_historical_dataset(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    expected = create_historical_dataset()
    service = build_portfolio_service()

    assert isinstance(service.risk, HistoricalRiskEngine)
    assert isinstance(service.risk.dataset, type(expected))
    assert isinstance(service.risk.dataset, FileHistoricalDataset)
    assert service.risk.dataset.dataset_id == DEMO_HISTORICAL_DATASET_ID
    assert expected.dataset_id == DEMO_HISTORICAL_DATASET_ID


def test_factory_default_spec_is_demo_dataset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    service = build_portfolio_service()
    spec = resolve_run_spec(risk_engine=service.risk)

    assert spec.historical_dataset_id == DEMO_HISTORICAL_DATASET_ID
    assert spec.historical_dataset_version == DEFAULT_HISTORICAL_DATASET_VERSION
    assert spec.as_of is None
    assert spec.calculation_config is not None
    assert spec.calculation_config.observations == service.risk.observations
    assert spec.calculation_config.seed == service.risk.seed


def test_factory_synthetic_env_uses_stable_id(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RISKFORGE_HISTORICAL_DATASET", "synthetic")
    service = build_portfolio_service()
    spec = resolve_run_spec(risk_engine=service.risk)

    assert isinstance(service.risk.dataset, SyntheticHistoricalDataset)
    assert spec.historical_dataset_id == SYNTHETIC_HISTORICAL_DATASET_ID
    assert spec.historical_dataset_version == DEFAULT_HISTORICAL_DATASET_VERSION
    assert spec.calculation_config is not None
    assert spec.calculation_config.seed == service.risk.seed
    assert spec.calculation_config.observations == service.risk.observations
