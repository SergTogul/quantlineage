"""G4: freeze public history into HistoricalDataset (no live network, no new VaR engine)."""

from __future__ import annotations

import ast
import csv
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.market.ingestion.errors import NotFoundError
from app.market.ingestion.models import (
    NORMALIZATION_VERSION,
    DataQualitySummary,
    DataSourceMetadata,
    Frequency,
    HistoricalPoint,
    HistoricalSeries,
    InstrumentRef,
    MacroSeriesRef,
)
from app.market.quality import MIN_OBSERVATIONS
from app.risk.factor_panel import factor_panel_from_dataset
from app.risk.historical_data import (
    DEMO_MULTI_FACTOR_DATASET_ID,
    PerFactorFileHistoricalDataset,
    create_historical_dataset,
)
from app.risk.shock_units import decimal_rate_to_bps
from app.services.risk_factories import (
    build_historical_risk_engine,
    dataset_identity,
    resolve_dataset_source,
    resolve_run_spec,
)

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
FORBIDDEN_ADAPTERS = frozenset(
    {
        "app.market.ingestion.yahoo",
        "app.market.ingestion.fred",
    }
)

_LEVEL_DATES = (
    date(2021, 1, 4),
    date(2021, 1, 5),
    date(2021, 1, 6),
    date(2021, 1, 7),
    date(2021, 1, 8),
    date(2021, 1, 11),
)
_START = _LEVEL_DATES[0]
_END = _LEVEL_DATES[-1]
_AAPL_EXTRA = date(2021, 1, 12)

# Distinct level paths so AAPL≠MSFT returns and DGS2≠DGS10 bp moves.
_EQUITY_LEVELS: dict[str, tuple[float, ...]] = {
    "equity:US:AAPL": (100.0, 101.0, 102.0, 103.0, 104.0, 105.0),
    "equity:US:MSFT": (200.0, 204.0, 208.0, 212.0, 216.0, 220.0),
    "equity:US:NVDA": (50.0, 51.0, 52.0, 53.0, 54.0, 55.0),
    "equity:US:SPY": (400.0, 402.0, 404.0, 406.0, 408.0, 410.0),
}
_RATE_LEVELS: dict[str, tuple[float, ...]] = {
    "macro:FRED:DGS2": (4.25, 4.30, 4.35, 4.40, 4.45, 4.50),
    "macro:FRED:DGS5": (4.00, 4.02, 4.04, 4.06, 4.08, 4.10),
    "macro:FRED:DGS10": (1.00, 1.10, 1.20, 1.30, 1.40, 1.50),
}


def _metadata(
    *,
    source: str,
    source_symbol: str,
    unit: str,
    adjustment: str,
    points: list[HistoricalPoint],
) -> DataSourceMetadata:
    return DataSourceMetadata(
        source=source,
        source_symbol=source_symbol,
        unit=unit,
        currency="USD",
        frequency=Frequency.DAILY,
        adjustment=adjustment,
        retrieved_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        first_observation=points[0].observation_date,
        last_observation=points[-1].observation_date,
        observation_count=len(points),
        normalization_version=NORMALIZATION_VERSION,
    )


def _series(
    *,
    instrument_id: str,
    asset_type: str,
    source: str,
    source_symbol: str,
    unit: str,
    adjustment: str,
    pairs: list[tuple[date, float]],
) -> HistoricalSeries:
    points = [HistoricalPoint(observation_date=day, value=value) for day, value in pairs]
    return HistoricalSeries(
        instrument=InstrumentRef(
            instrument_id=instrument_id, asset_type=asset_type, currency="USD"
        ),
        points=points,
        metadata=_metadata(
            source=source,
            source_symbol=source_symbol,
            unit=unit,
            adjustment=adjustment,
            points=points,
        ),
        quality=DataQualitySummary(missing_count=0, duplicate_count=0, stale=False),
    )


def _equity_series(instrument_id: str, symbol: str, levels: tuple[float, ...]) -> HistoricalSeries:
    pairs = list(zip(_LEVEL_DATES, levels, strict=True))
    if instrument_id == "equity:US:AAPL":
        pairs.append((_AAPL_EXTRA, 106.0))
    return _series(
        instrument_id=instrument_id,
        asset_type="etf" if symbol == "SPY" else "equity",
        source="yahoo",
        source_symbol=symbol,
        unit="price",
        adjustment="adjusted",
        pairs=pairs,
    )


def _rate_series(instrument_id: str, series_id: str, levels: tuple[float, ...]) -> HistoricalSeries:
    pairs = list(zip(_LEVEL_DATES, levels, strict=True))
    return _series(
        instrument_id=instrument_id,
        asset_type="macro",
        source="fred",
        source_symbol=series_id,
        unit="percent",
        adjustment="none",
        pairs=pairs,
    )


def _default_equity_catalog() -> dict[str, HistoricalSeries]:
    symbols = {"equity:US:AAPL": "AAPL", "equity:US:MSFT": "MSFT", "equity:US:NVDA": "NVDA", "equity:US:SPY": "SPY"}
    return {
        instrument_id: _equity_series(instrument_id, symbol, _EQUITY_LEVELS[instrument_id])
        for instrument_id, symbol in symbols.items()
    }


def _default_macro_catalog() -> dict[str, HistoricalSeries]:
    series_ids = {"macro:FRED:DGS2": "DGS2", "macro:FRED:DGS5": "DGS5", "macro:FRED:DGS10": "DGS10"}
    return {
        instrument_id: _rate_series(instrument_id, series_id, _RATE_LEVELS[instrument_id])
        for instrument_id, series_id in series_ids.items()
    }


class FakeHistoryProvider:
    def __init__(self, catalog: dict[str, HistoricalSeries] | None = None) -> None:
        self.catalog = catalog if catalog is not None else _default_equity_catalog()
        self.calls = 0

    def fetch_history(
        self,
        instrument: InstrumentRef,
        *,
        start: date,
        end: date,
        frequency: Frequency,
    ) -> HistoricalSeries:
        self.calls += 1
        series = self.catalog.get(instrument.instrument_id)
        if series is None:
            raise NotFoundError(instrument.instrument_id)
        return series


class FakeMacroProvider:
    def __init__(self, catalog: dict[str, HistoricalSeries] | None = None) -> None:
        self.catalog = catalog if catalog is not None else _default_macro_catalog()
        self.calls = 0

    def fetch_series(self, series: MacroSeriesRef, *, start: date, end: date) -> HistoricalSeries:
        self.calls += 1
        found = self.catalog.get(series.instrument_id)
        if found is None:
            raise NotFoundError(series.instrument_id)
        return found


class ExplodingHistoryProvider:
    def fetch_history(self, *args: object, **kwargs: object) -> HistoricalSeries:
        raise AssertionError("HistoricalDataProvider must not be called after freeze")


class ExplodingMacroProvider:
    def fetch_series(self, *args: object, **kwargs: object) -> HistoricalSeries:
        raise AssertionError("MacroDataProvider must not be called after freeze")


def _wave_a_spec():
    from app.market.history.spec import WAVE_A_SPEC, PublicHistoryDatasetSpec

    return PublicHistoryDatasetSpec(
        dataset_name=WAVE_A_SPEC.dataset_name,
        dataset_id=WAVE_A_SPEC.dataset_id,
        start=_START,
        end=_END,
        frequency=WAVE_A_SPEC.frequency,
        alignment=WAVE_A_SPEC.alignment,
        min_aligned_returns=WAVE_A_SPEC.min_aligned_returns,
        normalization_version=WAVE_A_SPEC.normalization_version,
        factor_mappings=WAVE_A_SPEC.factor_mappings,
        provider_source=WAVE_A_SPEC.provider_source,
    )


def _freeze(tmp_path: Path, *, history=None, macro=None, spec=None):
    from app.market.history.freeze import freeze_public_history

    return freeze_public_history(
        history_provider=history if history is not None else FakeHistoryProvider(),
        macro_provider=macro if macro is not None else FakeMacroProvider(),
        output_dir=tmp_path,
        spec=spec if spec is not None else _wave_a_spec(),
    )


def test_wave_a_spec_locks_factor_mappings_and_identity() -> None:
    from app.market.history.spec import (
        WAVE_A_DATASET_ID,
        WAVE_A_FACTOR_MAPPINGS,
        WAVE_A_MIN_ALIGNED_RETURNS,
        WAVE_A_SPEC,
    )

    assert WAVE_A_DATASET_ID == "real:public:wave-a"
    assert WAVE_A_SPEC.dataset_id == WAVE_A_DATASET_ID
    assert WAVE_A_SPEC.frequency == Frequency.DAILY
    assert WAVE_A_SPEC.alignment == "intersection"
    assert WAVE_A_SPEC.min_aligned_returns == WAVE_A_MIN_ALIGNED_RETURNS == 5
    assert WAVE_A_MIN_ALIGNED_RETURNS == MIN_OBSERVATIONS
    assert WAVE_A_SPEC.normalization_version == "wave-a-v1"
    mapping = {item.instrument_id: item.factor_column for item in WAVE_A_FACTOR_MAPPINGS}
    assert mapping == {
        "equity:US:AAPL": "EquitySpot:AAPL",
        "equity:US:MSFT": "EquitySpot:MSFT",
        "equity:US:NVDA": "EquitySpot:NVDA",
        "equity:US:SPY": "EquitySpot:SPY",
        "macro:FRED:DGS2": "RateZero:USD:2Y",
        "macro:FRED:DGS5": "RateZero:USD:5Y",
        "macro:FRED:DGS10": "RateZero:USD:10Y",
    }
    assert "EURUSD" not in json.dumps(mapping)
    assert not any("FX" in column or "Vol" in column for column in mapping.values())


def test_equity_100_to_101_is_relative_return_0_01() -> None:
    from app.market.history.transforms import equity_relative_return

    result = equity_relative_return(100.0, 101.0)
    assert result == pytest.approx(0.01, abs=1e-15)
    assert result == pytest.approx(101.0 / 100.0 - 1.0, abs=1e-18)
    assert result != pytest.approx((101.0 - 100.0) / 10_000.0, abs=1e-12)
    assert result != pytest.approx(1.0, abs=1e-12)
    assert result != pytest.approx(0.01 * 100.0, abs=1e-12)


def test_fred_percent_4_25_to_snapshot_decimal_0_0425() -> None:
    from app.market.history.transforms import percent_level_to_decimal

    result = percent_level_to_decimal(4.25)
    assert result == pytest.approx(0.0425, abs=1e-15)
    assert result == pytest.approx(4.25 / 100.0, abs=1e-18)
    assert result != pytest.approx(4.25, abs=1e-12)
    assert result != pytest.approx(4.25 / 10_000.0, abs=1e-12)
    assert result != pytest.approx(4.25 * 100.0, abs=1e-9)


def test_fred_4_25_to_4_30_is_plus_5_bp_not_wrong_scales() -> None:
    from app.market.history.transforms import percent_level_move_to_bps, percent_level_to_decimal

    move = percent_level_move_to_bps(4.25, 4.30)
    expected = decimal_rate_to_bps(percent_level_to_decimal(4.30) - percent_level_to_decimal(4.25))
    assert move == pytest.approx(5.0, abs=1e-12)
    assert move == pytest.approx(expected, abs=1e-12)
    assert move != pytest.approx(500.0, abs=1e-9)
    assert move != pytest.approx(0.0005, abs=1e-12)
    assert move != pytest.approx(0.05, abs=1e-12)
    assert move != pytest.approx(4.30 - 4.25, abs=1e-12)


def test_freeze_writes_distinct_equity_and_rate_columns(tmp_path: Path) -> None:
    artifact = _freeze(tmp_path)
    with artifact.csv_path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [row["date"] for row in rows] == [day.isoformat() for day in _LEVEL_DATES[1:]]
    header = rows[0].keys()
    assert "EquitySpot:AAPL" in header
    assert "EquitySpot:MSFT" in header
    assert "RateZero:USD:2Y" in header
    assert "RateZero:USD:10Y" in header
    assert "FXSpot:EURUSD" not in header
    aapl = [float(row["EquitySpot:AAPL"]) for row in rows]
    msft = [float(row["EquitySpot:MSFT"]) for row in rows]
    dgs2 = [float(row["RateZero:USD:2Y"]) for row in rows]
    dgs10 = [float(row["RateZero:USD:10Y"]) for row in rows]
    assert aapl != msft
    assert dgs2 != dgs10
    assert aapl[0] == pytest.approx(0.01, abs=1e-12)
    assert dgs2[0] == pytest.approx(5.0, abs=1e-12)
    assert dgs10[0] == pytest.approx(10.0, abs=1e-12)


def test_freeze_csv_pins_exact_transforms_and_mutation_guards(tmp_path: Path) -> None:
    artifact = _freeze(tmp_path)
    with artifact.csv_path.open(newline="", encoding="utf-8") as fh:
        first = next(csv.DictReader(fh))
    aapl = float(first["EquitySpot:AAPL"])
    dgs2 = float(first["RateZero:USD:2Y"])
    assert aapl == pytest.approx(0.01, abs=1e-12)
    assert aapl != pytest.approx((101.0 - 100.0) / 10_000.0, abs=1e-12)
    assert aapl != pytest.approx(1.0, abs=1e-12)
    assert dgs2 == pytest.approx(5.0, abs=1e-12)
    assert dgs2 != pytest.approx(500.0, abs=1e-9)
    assert dgs2 != pytest.approx(0.0005, abs=1e-12)
    assert dgs2 != pytest.approx(0.05, abs=1e-12)


def test_missing_required_factor_fails_freeze(tmp_path: Path) -> None:
    from app.market.history.freeze import MissingRequiredFactorError

    catalog = _default_equity_catalog()
    del catalog["equity:US:NVDA"]
    with pytest.raises(MissingRequiredFactorError, match="equity:US:NVDA"):
        _freeze(tmp_path, history=FakeHistoryProvider(catalog))


def test_same_normalized_content_same_hash_changed_observation_new_hash(tmp_path: Path) -> None:
    first = _freeze(tmp_path / "a")
    second = _freeze(tmp_path / "b")
    assert first.dataset_id == second.dataset_id == "real:public:wave-a"
    assert first.dataset_version == second.dataset_version
    assert first.dataset_version != "v1"

    mutated_catalog = _default_equity_catalog()
    original = mutated_catalog["equity:US:AAPL"]
    mutated_points = list(original.points)
    mutated_points[1] = HistoricalPoint(observation_date=mutated_points[1].observation_date, value=101.5)
    mutated_catalog["equity:US:AAPL"] = original.model_copy(update={"points": mutated_points})
    third = _freeze(tmp_path / "c", history=FakeHistoryProvider(mutated_catalog))
    assert third.dataset_id == first.dataset_id
    assert third.dataset_version != first.dataset_version

    sidecar = json.loads(first.sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["dataset_id"] == first.dataset_id
    assert sidecar["dataset_version"] == first.dataset_version
    assert sidecar["normalization_version"] == "wave-a-v1"
    assert "transform_config" in sidecar
    assert "dropped_dates" in sidecar
    dropped = sidecar["dropped_dates"]["equity:US:AAPL"]
    assert _AAPL_EXTRA.isoformat() in dropped
    assert "retrieved_at" not in json.dumps({"dataset_version": first.dataset_version})


def test_freeze_then_factory_loads_by_id_without_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.market.history.artifact import PUBLIC_HISTORY_CSV_ENV
    from app.market.history.spec import WAVE_A_DATASET_ID

    history = FakeHistoryProvider()
    macro = FakeMacroProvider()
    artifact = _freeze(tmp_path, history=history, macro=macro)
    assert history.calls > 0
    assert macro.calls > 0

    monkeypatch.setenv(PUBLIC_HISTORY_CSV_ENV, str(artifact.csv_path))
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)

    exploding_history = ExplodingHistoryProvider()
    exploding_macro = ExplodingMacroProvider()
    assert exploding_history is not history
    assert exploding_macro is not macro

    source = resolve_dataset_source(WAVE_A_DATASET_ID)
    dataset = create_historical_dataset(WAVE_A_DATASET_ID)
    assert isinstance(dataset, PerFactorFileHistoricalDataset)
    assert dataset.dataset_id == WAVE_A_DATASET_ID
    assert dataset.dataset_version == artifact.dataset_version
    panel = factor_panel_from_dataset(dataset)
    assert panel.n_observations == 5
    engine = build_historical_risk_engine(historical_dataset_id=WAVE_A_DATASET_ID)
    assert engine.dataset.dataset_id == WAVE_A_DATASET_ID
    used_id, used_version = dataset_identity(engine.dataset)
    assert used_id == artifact.dataset_id
    assert used_version == artifact.dataset_version
    assert Path(source).resolve() == artifact.csv_path.resolve()
    assert "EquitySpot:AAPL" in dataset.columns
    assert "RateZero:USD:2Y" in dataset.columns


def test_riskrun_factory_identity_matches_frozen_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.market.history.artifact import PUBLIC_HISTORY_CSV_ENV
    from app.market.history.spec import WAVE_A_DATASET_ID

    artifact = _freeze(tmp_path)
    monkeypatch.setenv(PUBLIC_HISTORY_CSV_ENV, str(artifact.csv_path))
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)

    spec = resolve_run_spec({"historical_dataset_id": WAVE_A_DATASET_ID})
    assert spec.historical_dataset_id == WAVE_A_DATASET_ID
    assert spec.historical_dataset_id != DEMO_MULTI_FACTOR_DATASET_ID
    assert spec.historical_dataset_version == artifact.dataset_version
    rebound = build_historical_risk_engine(historical_dataset_id=spec.historical_dataset_id)
    bound_id, bound_version = dataset_identity(rebound.dataset)
    assert bound_id == spec.historical_dataset_id == artifact.dataset_id
    assert bound_version == spec.historical_dataset_version == artifact.dataset_version


def test_default_dataset_stays_demo_multi_factor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    monkeypatch.delenv("QUANTLINEAGE_PUBLIC_HISTORY_CSV", raising=False)
    dataset = create_historical_dataset()
    engine = build_historical_risk_engine()
    assert dataset.dataset_id == DEMO_MULTI_FACTOR_DATASET_ID
    assert engine.dataset.dataset_id == DEMO_MULTI_FACTOR_DATASET_ID


def test_quant_core_and_freeze_do_not_import_provider_adapters() -> None:
    freeze_root = APP_ROOT / "market" / "history"
    assert freeze_root.is_dir()
    for package in ("risk", "pricing"):
        for py in (APP_ROOT / package).rglob("*.py"):
            imported = _import_targets(py)
            hit = imported & FORBIDDEN_ADAPTERS
            assert not hit, f"{py}: {sorted(hit)}"
    for py in freeze_root.rglob("*.py"):
        imported = _import_targets(py)
        hit = imported & FORBIDDEN_ADAPTERS
        assert not hit, f"{py}: {sorted(hit)}"
        for name in imported:
            assert not name.startswith("app.risk.historical") or name in {
                "app.risk.historical_data",
            }, f"{py} imports {name}"
        assert "app.risk.historical" not in imported
        assert "httpx" not in {name.split(".", 1)[0] for name in imported}
        assert "fastapi" not in {name.split(".", 1)[0] for name in imported}


def test_importing_historical_engine_does_not_load_adapters_or_call_providers() -> None:
    for name in list(sys.modules):
        if name in FORBIDDEN_ADAPTERS or name.startswith("app.market.ingestion.yahoo"):
            del sys.modules[name]
        if name.startswith("app.market.ingestion.fred"):
            del sys.modules[name]

    import app.risk.historical  # noqa: F401
    import app.risk.historical_data  # noqa: F401
    from app.services import risk_factories  # noqa: F401

    loaded = sorted(name for name in FORBIDDEN_ADAPTERS if name in sys.modules)
    assert loaded == [], f"quant/factory import loaded adapters: {loaded}"
    assert "app.market.ingestion.yahoo" not in sys.modules
    assert "app.market.ingestion.fred" not in sys.modules


def _import_targets(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found
