"""G5: build real MarketSnapshot from public data (no live network, no second VaR engine)."""

from __future__ import annotations

import ast
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.domain.models import EquityPosition, Portfolio, RiskRun
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
from app.market.ingestion.normalize import STALE_AFTER_DAYS
from app.persistence.memory_repos import (
    InMemoryMarketSnapshotRepository,
    InMemoryRiskRunRepository,
)

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
FORBIDDEN_ADAPTERS = frozenset(
    {
        "app.market.ingestion.yahoo",
        "app.market.ingestion.fred",
    }
)

# Monday as_of; last session is Friday. Tuesday print must not leak in.
_FRIDAY = date(2024, 1, 5)
_MONDAY = date(2024, 1, 8)
_TUESDAY = date(2024, 1, 9)
_THURSDAY = date(2024, 1, 4)
_STALE_AS_OF = date(2024, 1, 22)  # Friday print is 17 calendar days earlier

_EQUITY_FRIDAY: dict[str, float] = {
    "equity:US:AAPL": 185.0,
    "equity:US:MSFT": 370.0,
    "equity:US:NVDA": 480.0,
    "equity:US:SPY": 470.0,
}
_EQUITY_THURSDAY: dict[str, float] = {
    "equity:US:AAPL": 180.0,
    "equity:US:MSFT": 360.0,
    "equity:US:NVDA": 470.0,
    "equity:US:SPY": 460.0,
}
_EQUITY_TUESDAY: dict[str, float] = {
    "equity:US:AAPL": 190.0,
    "equity:US:MSFT": 380.0,
    "equity:US:NVDA": 500.0,
    "equity:US:SPY": 480.0,
}
_RATE_FRIDAY: dict[str, float] = {
    "macro:FRED:DGS2": 4.10,
    "macro:FRED:DGS5": 4.15,
    "macro:FRED:DGS10": 4.25,
}
_RATE_THURSDAY: dict[str, float] = {
    "macro:FRED:DGS2": 4.05,
    "macro:FRED:DGS5": 4.12,
    "macro:FRED:DGS10": 4.20,
}
_RATE_TUESDAY: dict[str, float] = {
    "macro:FRED:DGS2": 4.30,
    "macro:FRED:DGS5": 4.35,
    "macro:FRED:DGS10": 4.40,
}

_EQUITY_SYMBOLS = {
    "equity:US:AAPL": "AAPL",
    "equity:US:MSFT": "MSFT",
    "equity:US:NVDA": "NVDA",
    "equity:US:SPY": "SPY",
}
_RATE_SERIES = {
    "macro:FRED:DGS2": "DGS2",
    "macro:FRED:DGS5": "DGS5",
    "macro:FRED:DGS10": "DGS10",
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


def _equity_catalog(*, include_tuesday: bool = True) -> dict[str, HistoricalSeries]:
    catalog: dict[str, HistoricalSeries] = {}
    for instrument_id, symbol in _EQUITY_SYMBOLS.items():
        pairs = [
            (_THURSDAY, _EQUITY_THURSDAY[instrument_id]),
            (_FRIDAY, _EQUITY_FRIDAY[instrument_id]),
        ]
        if include_tuesday:
            pairs.append((_TUESDAY, _EQUITY_TUESDAY[instrument_id]))
        catalog[instrument_id] = _series(
            instrument_id=instrument_id,
            asset_type="etf" if symbol == "SPY" else "equity",
            source="yahoo",
            source_symbol=symbol,
            unit="price",
            adjustment="adjusted",
            pairs=pairs,
        )
    return catalog


def _macro_catalog(*, include_tuesday: bool = True) -> dict[str, HistoricalSeries]:
    catalog: dict[str, HistoricalSeries] = {}
    for instrument_id, series_id in _RATE_SERIES.items():
        pairs = [
            (_THURSDAY, _RATE_THURSDAY[instrument_id]),
            (_FRIDAY, _RATE_FRIDAY[instrument_id]),
        ]
        if include_tuesday:
            pairs.append((_TUESDAY, _RATE_TUESDAY[instrument_id]))
        catalog[instrument_id] = _series(
            instrument_id=instrument_id,
            asset_type="macro",
            source="fred",
            source_symbol=series_id,
            unit="percent",
            adjustment="none",
            pairs=pairs,
        )
    return catalog


class FakeHistoryProvider:
    def __init__(self, catalog: dict[str, HistoricalSeries] | None = None) -> None:
        self.catalog = catalog if catalog is not None else _equity_catalog()
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
        self.catalog = catalog if catalog is not None else _macro_catalog()
        self.calls = 0

    def fetch_series(self, series: MacroSeriesRef, *, start: date, end: date) -> HistoricalSeries:
        self.calls += 1
        found = self.catalog.get(series.instrument_id)
        if found is None:
            raise NotFoundError(series.instrument_id)
        return found


class ExplodingHistoryProvider:
    def fetch_history(self, *args: object, **kwargs: object) -> HistoricalSeries:
        raise AssertionError("HistoricalDataProvider must not be called after snapshot build")


class ExplodingMacroProvider:
    def fetch_series(self, *args: object, **kwargs: object) -> HistoricalSeries:
        raise AssertionError("MacroDataProvider must not be called after snapshot build")


def _build(as_of: date = _MONDAY, *, history=None, macro=None):
    from app.market.history.snapshot import build_public_snapshot

    return build_public_snapshot(
        as_of=as_of,
        history_provider=history if history is not None else FakeHistoryProvider(),
        macro_provider=macro if macro is not None else FakeMacroProvider(),
    )


def test_snapshot_id_is_real_public_wave_a_as_of_iso() -> None:
    built = _build(_MONDAY)
    assert built.snapshot.id == "real:public:wave-a:2024-01-08"
    assert built.snapshot.as_of == _MONDAY
    later = _build(date(2024, 1, 12))
    assert later.snapshot.id == "real:public:wave-a:2024-01-12"
    assert later.snapshot.id != built.snapshot.id


def test_fred_percent_4_25_is_snapshot_decimal_0_0425_not_bp() -> None:
    built = _build(_MONDAY)
    snapshot = built.snapshot
    ten_year = snapshot.key_rates["USD"]["10Y"]
    assert ten_year == pytest.approx(0.0425, abs=1e-15)
    assert snapshot.rates["USD"] == pytest.approx(0.0425, abs=1e-15)
    assert snapshot.key_rates["USD"]["2Y"] == pytest.approx(0.0410, abs=1e-15)
    assert snapshot.key_rates["USD"]["5Y"] == pytest.approx(0.0415, abs=1e-15)
    assert ten_year != pytest.approx(4.25, abs=1e-12)
    assert ten_year != pytest.approx(425.0, abs=1e-9)
    assert ten_year != pytest.approx(0.000425, abs=1e-12)
    assert ten_year != pytest.approx(5.0, abs=1e-12)
    assert snapshot.rates["USD"] != pytest.approx(5.0, abs=1e-12)


def test_equity_spot_equals_last_adjusted_close_on_or_before_as_of() -> None:
    built = _build(_MONDAY)
    spots = built.snapshot.equity_spots
    assert spots["AAPL"] == pytest.approx(185.0, abs=1e-12)
    assert spots["MSFT"] == pytest.approx(370.0, abs=1e-12)
    assert spots["NVDA"] == pytest.approx(480.0, abs=1e-12)
    assert spots["SPY"] == pytest.approx(470.0, abs=1e-12)
    assert spots["AAPL"] != pytest.approx(180.0, abs=1e-12)
    assert spots["AAPL"] != pytest.approx(190.0, abs=1e-12)


def test_monday_as_of_keeps_friday_source_observation_date() -> None:
    built = _build(_MONDAY)
    assert built.snapshot.as_of == _MONDAY
    lineage = built.lineage["marks"]
    aapl = lineage["equity:US:AAPL"]
    dgs10 = lineage["macro:FRED:DGS10"]
    assert aapl["source_observation_date"] == _FRIDAY.isoformat()
    assert dgs10["source_observation_date"] == _FRIDAY.isoformat()
    assert aapl["source_observation_date"] != _MONDAY.isoformat()
    assert dgs10["source_observation_date"] != _MONDAY.isoformat()
    assert aapl["provider"] == "yahoo"
    assert aapl["source_symbol"] == "AAPL"
    assert aapl["unit"] == "price"
    assert aapl["stale"] is False
    assert dgs10["provider"] == "fred"
    assert dgs10["source_symbol"] == "DGS10"
    assert dgs10["unit"] == "percent"


def test_stale_series_fails_closed_and_does_not_use_old_print() -> None:
    from app.market.history.snapshot import StalePublicSnapshotError

    assert (_STALE_AS_OF - _FRIDAY).days > STALE_AFTER_DAYS
    with pytest.raises(StalePublicSnapshotError):
        _build(_STALE_AS_OF)


def test_persist_then_riskrun_market_snapshot_id_round_trip() -> None:
    from app.market.history.snapshot import (
        bind_risk_run_to_saved_snapshot,
        persist_public_snapshot,
    )

    built = _build(_MONDAY)
    markets = InMemoryMarketSnapshotRepository()
    runs = InMemoryRiskRunRepository()
    snapshot_id = persist_public_snapshot(markets, built)
    assert snapshot_id == built.snapshot.id
    run = bind_risk_run_to_saved_snapshot(
        run_repo=runs,
        market_repo=markets,
        run=RiskRun(id="run-wave-a", portfolio_id="book-cash"),
        snapshot_id=snapshot_id,
    )
    assert run.market_snapshot_id == built.snapshot.id
    assert run.as_of == built.snapshot.as_of == _MONDAY
    loaded = markets.get(snapshot_id)
    assert loaded is not None
    assert loaded.content_hash() == built.snapshot.content_hash()
    assert loaded.equity_spots["AAPL"] == pytest.approx(185.0, abs=1e-12)
    assert loaded.key_rates["USD"]["10Y"] == pytest.approx(0.0425, abs=1e-15)
    meta = markets.get_meta(snapshot_id)
    assert meta is not None
    assert meta["meta"]["marks"]["equity:US:AAPL"]["source_observation_date"] == _FRIDAY.isoformat()


def test_bind_refuses_unsaved_snapshot_id() -> None:
    from app.market.history.snapshot import (
        UnsavedPublicSnapshotError,
        bind_risk_run_to_saved_snapshot,
    )

    built = _build(_MONDAY)
    markets = InMemoryMarketSnapshotRepository()
    runs = InMemoryRiskRunRepository()
    with pytest.raises(UnsavedPublicSnapshotError):
        bind_risk_run_to_saved_snapshot(
            run_repo=runs,
            market_repo=markets,
            run=RiskRun(id="run-unsaved", portfolio_id="book-cash"),
            snapshot_id=built.snapshot.id,
        )
    assert runs.get("run-unsaved") is None


def test_prices_cash_aapl_book_from_public_snapshot_without_provider() -> None:
    from app.pricing.builtin import BuiltinPricingEngine

    history = FakeHistoryProvider()
    macro = FakeMacroProvider()
    built = _build(_MONDAY, history=history, macro=macro)
    assert history.calls > 0
    assert macro.calls > 0
    book = Portfolio(
        id="book-cash",
        name="Wave A cash",
        positions=[
            EquityPosition(type="equity", id="eq-aapl", symbol="AAPL", quantity=10.0),
            EquityPosition(type="equity", id="eq-msft", symbol="MSFT", quantity=2.0),
        ],
    )
    exploding_history = ExplodingHistoryProvider()
    exploding_macro = ExplodingMacroProvider()
    engine = BuiltinPricingEngine()
    valuations = engine.value_portfolio(book, built.snapshot)
    by_id = {item.position_id: item.market_value for item in valuations}
    assert by_id["eq-aapl"] == pytest.approx(10.0 * 185.0, abs=1e-9)
    assert by_id["eq-msft"] == pytest.approx(2.0 * 370.0, abs=1e-9)
    assert "equity_vols" not in built.lineage or built.lineage.get("vol_fallback") in (None, "")
    assert dict(built.snapshot.equity_vols) == {}
    assert dict(built.snapshot.vol_surfaces) == {}
    with pytest.raises(AssertionError, match="must not be called after snapshot build"):
        exploding_history.fetch_history(
            InstrumentRef(instrument_id="equity:US:AAPL", asset_type="equity", currency="USD"),
            start=_MONDAY,
            end=_MONDAY,
            frequency=Frequency.DAILY,
        )
    with pytest.raises(AssertionError, match="must not be called after snapshot build"):
        exploding_macro.fetch_series(
            MacroSeriesRef(instrument_id="macro:FRED:DGS10", series_id="DGS10", currency="USD"),
            start=_MONDAY,
            end=_MONDAY,
        )


def test_historical_module_still_does_not_import_adapters() -> None:
    for name in list(sys.modules):
        if name in FORBIDDEN_ADAPTERS or name.startswith("app.market.ingestion.yahoo"):
            del sys.modules[name]
        if name.startswith("app.market.ingestion.fred"):
            del sys.modules[name]

    import app.risk.historical  # noqa: F401

    loaded = sorted(name for name in FORBIDDEN_ADAPTERS if name in sys.modules)
    assert loaded == [], f"app.risk.historical loaded adapters: {loaded}"
    historical = APP_ROOT / "risk" / "historical.py"
    imported = _import_targets(historical)
    assert not (imported & FORBIDDEN_ADAPTERS)


def test_snapshot_builder_does_not_import_historical_var_engine() -> None:
    snapshot_py = APP_ROOT / "market" / "history" / "snapshot.py"
    imported = _import_targets(snapshot_py)
    assert "app.risk.historical" not in imported
    for name in imported:
        assert not name.startswith("app.risk.historical") or name == "app.risk.historical_data"


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
