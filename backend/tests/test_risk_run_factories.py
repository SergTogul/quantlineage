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
    file_csv_dataset_id,
)
from app.services.risk_factories import (
    DEFAULT_HISTORICAL_DATASET_VERSION,
    SYNTHETIC_HISTORICAL_DATASET_ID,
    build_portfolio_service,
    portfolio_service_for_spec,
    resolve_dataset_source,
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


def test_resolve_run_spec_rejects_unknown_dataset_id(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    service = build_portfolio_service()
    with pytest.raises(ValueError, match="historical_dataset_id"):
        resolve_run_spec(
            {"historical_dataset_id": "not-a-real-dataset"},
            risk_engine=service.risk,
        )


def test_resolve_run_spec_rebinds_synthetic_from_demo_engine(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    service = build_portfolio_service()
    assert service.risk.dataset.dataset_id == DEMO_HISTORICAL_DATASET_ID

    spec = resolve_run_spec(
        {"historical_dataset_id": SYNTHETIC_HISTORICAL_DATASET_ID},
        risk_engine=service.risk,
    )
    assert spec.historical_dataset_id == SYNTHETIC_HISTORICAL_DATASET_ID
    assert spec.historical_dataset_version == DEFAULT_HISTORICAL_DATASET_VERSION

    from app.services.risk_factories import build_historical_risk_engine_for_spec

    rebound = build_historical_risk_engine_for_spec(spec)
    assert isinstance(rebound.dataset, SyntheticHistoricalDataset)
    assert not isinstance(rebound.dataset, FileHistoricalDataset)


def _write_mini_csv(path, *, equity_return: float = 0.01) -> None:
    path.write_text(
        "date,equity_return,vol_move,rate_move_bps,fx_return\n"
        f"2024-01-02,{equity_return},0.0,1.0,0.001\n"
        "2024-01-03,-0.02,0.05,-2.0,-0.001\n",
        encoding="utf-8",
    )


def test_csv_dataset_identity_is_path_derived(tmp_path):
    path_a = tmp_path / "a.csv"
    path_b = tmp_path / "b.csv"
    _write_mini_csv(path_a, equity_return=0.01)
    _write_mini_csv(path_b, equity_return=-0.05)

    ds_a = create_historical_dataset(str(path_a))
    ds_b = create_historical_dataset(str(path_b))
    assert isinstance(ds_a, FileHistoricalDataset)
    assert isinstance(ds_b, FileHistoricalDataset)
    assert ds_a.dataset_id == file_csv_dataset_id(path_a)
    assert ds_b.dataset_id == file_csv_dataset_id(path_b)
    assert ds_a.dataset_id != ds_b.dataset_id
    assert ds_a.dataset_id != "file"
    assert ds_a.source_path == str(path_a.resolve())
    assert ds_b.source_path == str(path_b.resolve())


def test_portfolio_service_for_spec_rebinds_between_csv_paths(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    """Process CSV A + request CSV B must rebind to B — never silently keep A."""
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    path_a = tmp_path / "engine_a.csv"
    path_b = tmp_path / "request_b.csv"
    _write_mini_csv(path_a, equity_return=0.01)
    _write_mini_csv(path_b, equity_return=-0.05)

    base = build_portfolio_service(historical_dataset_id=str(path_a))
    assert isinstance(base.risk.dataset, FileHistoricalDataset)
    assert base.risk.dataset.source_path == str(path_a.resolve())

    spec = resolve_run_spec(
        {"historical_dataset_id": str(path_b)},
        risk_engine=base.risk,
    )
    assert spec.historical_dataset_id == file_csv_dataset_id(path_b)
    assert spec.historical_dataset_id != file_csv_dataset_id(path_a)

    rebound = portfolio_service_for_spec(base, spec)
    assert rebound is not base
    assert isinstance(rebound.risk.dataset, FileHistoricalDataset)
    assert rebound.risk.dataset.source_path == str(path_b.resolve())
    assert rebound.risk.dataset.dataset_id == file_csv_dataset_id(path_b)


def test_resolve_dataset_source_rejects_bare_file_id():
    with pytest.raises(ValueError, match="ambiguous historical_dataset_id 'file'"):
        resolve_dataset_source("file")


def test_resolve_dataset_source_rejects_missing_csv(tmp_path):
    missing = tmp_path / "does-not-exist.csv"
    with pytest.raises(ValueError, match="historical dataset CSV not found"):
        resolve_dataset_source(str(missing))


def test_resolve_run_spec_rejects_bare_file_against_demo_engine(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    service = build_portfolio_service()
    with pytest.raises(ValueError, match="ambiguous historical_dataset_id 'file'"):
        resolve_run_spec(
            {"historical_dataset_id": "file"},
            risk_engine=service.risk,
        )
