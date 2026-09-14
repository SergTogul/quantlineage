"""G8: Wave A hostile gap tests. Fake providers only; no live Yahoo/FRED."""

from __future__ import annotations

import ast
import inspect
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from tests.test_ingestion_yahoo import _CHART_AAPL, _yahoo
from tests.test_public_history_dataset import (
    FakeHistoryProvider as FreezeHistory,
)
from tests.test_public_history_dataset import (
    FakeMacroProvider as FreezeMacro,
)
from tests.test_public_history_dataset import (
    _freeze,
    _wave_a_spec,
)
from tests.test_public_market_snapshot import (
    _EQUITY_FRIDAY,
    _FRIDAY,
    _MONDAY,
    _RATE_FRIDAY,
    _build,
    _equity_catalog,
    _macro_catalog,
)
from tests.test_public_market_snapshot import (
    FakeHistoryProvider as SnapshotHistory,
)
from tests.test_public_market_snapshot import (
    FakeMacroProvider as SnapshotMacro,
)

from app.domain.models import EquityPosition, Portfolio, RiskRun
from app.market.ingestion.errors import AuthorizationError
from app.market.ingestion.models import Frequency, InstrumentRef
from app.persistence.memory_repos import (
    InMemoryMarketSnapshotRepository,
    InMemoryRiskRunRepository,
)

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
REPO_ROOT = Path(__file__).resolve().parents[2]
FORBIDDEN_ADAPTERS = frozenset(
    {
        "app.market.ingestion.yahoo",
        "app.market.ingestion.fred",
    }
)
_SECRET = "super-secret-fred-key"
_AAPL = InstrumentRef(instrument_id="equity:US:AAPL", asset_type="equity", currency="USD")
_START = date(2021, 1, 4)
_END = date(2021, 1, 6)
_SATURDAY = date(2024, 1, 6)
_BEFORE_HISTORY = date(2019, 6, 15)


def _drop_adapter_modules() -> None:
    for name in list(sys.modules):
        if (
            name in FORBIDDEN_ADAPTERS
            or name.startswith("app.market.ingestion.yahoo")
            or name.startswith("app.market.ingestion.fred")
        ):
            sys.modules.pop(name, None)


def _cash_book() -> Portfolio:
    return Portfolio(
        id="book-cash",
        name="Wave A cash",
        positions=[
            EquityPosition(type="equity", id="eq-aapl", symbol="AAPL", quantity=10.0),
            EquityPosition(type="equity", id="eq-msft", symbol="MSFT", quantity=2.0),
        ],
    )


def _fred(handler):
    from app.market.ingestion.fred import FredAdapter

    client = httpx.Client(transport=httpx.MockTransport(handler), timeout=10.0)
    return FredAdapter(client=client, api_key=_SECRET)


def test_snapshot_as_of_before_history_fails_closed_and_does_not_invent_print() -> None:
    from app.market.history.snapshot import MissingPublicSnapshotMarkError

    with pytest.raises(MissingPublicSnapshotMarkError, match="on or before"):
        _build(_BEFORE_HISTORY)
    with pytest.raises(MissingPublicSnapshotMarkError):
        _build(date(2023, 12, 1))


def test_freeze_end_before_history_fails_closed(tmp_path: Path) -> None:
    from app.market.history.freeze import MissingRequiredFactorError
    from app.market.history.spec import WAVE_A_SPEC, PublicHistoryDatasetSpec

    spec = PublicHistoryDatasetSpec(
        dataset_name=WAVE_A_SPEC.dataset_name,
        dataset_id=WAVE_A_SPEC.dataset_id,
        start=date(2019, 1, 2),
        end=_BEFORE_HISTORY,
        frequency=WAVE_A_SPEC.frequency,
        alignment=WAVE_A_SPEC.alignment,
        min_aligned_returns=WAVE_A_SPEC.min_aligned_returns,
        normalization_version=WAVE_A_SPEC.normalization_version,
        factor_mappings=WAVE_A_SPEC.factor_mappings,
        provider_source=WAVE_A_SPEC.provider_source,
    )
    with pytest.raises(MissingRequiredFactorError):
        _freeze(tmp_path, spec=spec)
    assert not (tmp_path / "real_public_wave_a.csv").exists()


def test_saturday_as_of_keeps_friday_last_print() -> None:
    built = _build(_SATURDAY)
    assert built.snapshot.as_of == _SATURDAY
    assert built.snapshot.id == f"real:public:wave-a:2024-01-06:{built.snapshot.content_hash()}"
    lineage = built.lineage["marks"]
    assert lineage["equity:US:AAPL"]["source_observation_date"] == _FRIDAY.isoformat()
    assert lineage["macro:FRED:DGS10"]["source_observation_date"] == _FRIDAY.isoformat()
    assert built.snapshot.equity_spots["AAPL"] == pytest.approx(_EQUITY_FRIDAY["equity:US:AAPL"])
    assert built.snapshot.key_rates["USD"]["10Y"] == pytest.approx(_RATE_FRIDAY["macro:FRED:DGS10"] / 100.0)


def test_retrieved_at_next_calendar_day_does_not_shift_observation_date() -> None:
    retrieved = datetime(2024, 1, 9, 16, 30, tzinfo=UTC)
    equities = {}
    for instrument_id, series in _equity_catalog().items():
        equities[instrument_id] = series.model_copy(
            update={"metadata": series.metadata.model_copy(update={"retrieved_at": retrieved})}
        )
    macros = {}
    for instrument_id, series in _macro_catalog().items():
        macros[instrument_id] = series.model_copy(
            update={"metadata": series.metadata.model_copy(update={"retrieved_at": retrieved})}
        )
    built = _build(
        _MONDAY,
        history=SnapshotHistory(equities),
        macro=SnapshotMacro(macros),
    )
    aapl = built.lineage["marks"]["equity:US:AAPL"]
    assert aapl["source_observation_date"] == _FRIDAY.isoformat()
    assert aapl["source_observation_date"] != retrieved.date().isoformat()
    assert built.snapshot.as_of == _MONDAY
    assert built.snapshot.equity_spots["AAPL"] == pytest.approx(185.0)


def test_yahoo_unix_timestamps_are_utc_calendar_dates_not_local_tz() -> None:
    yahoo_src = (APP_ROOT / "market" / "ingestion" / "yahoo.py").read_text(encoding="utf-8")
    assert "datetime.fromtimestamp(int(ts), UTC).date()" in yahoo_src
    utc_dates = [
        datetime.fromtimestamp(1609718400, UTC).date(),
        datetime.fromtimestamp(1609804800, UTC).date(),
        datetime.fromtimestamp(1609891200, UTC).date(),
    ]
    assert utc_dates[0] == date(2021, 1, 4)
    pacific = datetime.fromtimestamp(1609718400, UTC).astimezone(
        __import__("zoneinfo").ZoneInfo("America/Los_Angeles")
    )
    assert pacific.date() == date(2021, 1, 3)
    series = _yahoo(lambda request: httpx.Response(200, json=_CHART_AAPL)).fetch_history(
        _AAPL, start=_START, end=_END, frequency=Frequency.DAILY
    )
    assert [point.observation_date for point in series.points] == utc_dates[:2]
    assert series.metadata.retrieved_at.tzinfo is UTC


def test_mapping_dgs10_onto_equity_spot_cannot_freeze_wave_a(tmp_path: Path) -> None:
    from app.market.history.freeze import FreezeError
    from app.market.history.spec import WAVE_A_SPEC, FactorMapping, PublicHistoryDatasetSpec

    swapped = FactorMapping(
        instrument_id="macro:FRED:DGS10",
        factor_column="EquitySpot:AAPL",
        provider="fred",
        source_symbol="DGS10",
        asset_type="macro",
        unit="percent",
        kind="rate",
    )
    mappings = tuple(
        swapped if item.instrument_id == "macro:FRED:DGS10" else item
        for item in WAVE_A_SPEC.factor_mappings
    )
    spec = PublicHistoryDatasetSpec(
        dataset_name=WAVE_A_SPEC.dataset_name,
        dataset_id=WAVE_A_SPEC.dataset_id,
        start=_wave_a_spec().start,
        end=_wave_a_spec().end,
        frequency=WAVE_A_SPEC.frequency,
        alignment=WAVE_A_SPEC.alignment,
        min_aligned_returns=WAVE_A_SPEC.min_aligned_returns,
        normalization_version=WAVE_A_SPEC.normalization_version,
        factor_mappings=mappings,
        provider_source=WAVE_A_SPEC.provider_source,
    )
    with pytest.raises(FreezeError, match="canonical mapping"):
        _freeze(tmp_path, spec=spec)
    assert not (tmp_path / "real_public_wave_a.csv").exists()


def test_mapping_aapl_onto_rate_zero_cannot_freeze_wave_a(tmp_path: Path) -> None:
    from app.market.history.freeze import FreezeError
    from app.market.history.spec import WAVE_A_SPEC, FactorMapping, PublicHistoryDatasetSpec

    swapped = FactorMapping(
        instrument_id="equity:US:AAPL",
        factor_column="RateZero:USD:10Y",
        provider="yahoo",
        source_symbol="AAPL",
        asset_type="equity",
        unit="price",
        kind="equity",
    )
    mappings = tuple(
        swapped if item.instrument_id == "equity:US:AAPL" else item
        for item in WAVE_A_SPEC.factor_mappings
    )
    spec = PublicHistoryDatasetSpec(
        dataset_name=WAVE_A_SPEC.dataset_name,
        dataset_id=WAVE_A_SPEC.dataset_id,
        start=_wave_a_spec().start,
        end=_wave_a_spec().end,
        frequency=WAVE_A_SPEC.frequency,
        alignment=WAVE_A_SPEC.alignment,
        min_aligned_returns=WAVE_A_SPEC.min_aligned_returns,
        normalization_version=WAVE_A_SPEC.normalization_version,
        factor_mappings=mappings,
        provider_source=WAVE_A_SPEC.provider_source,
    )
    with pytest.raises(FreezeError, match="canonical mapping"):
        _freeze(tmp_path, spec=spec)


def test_series_provider_metadata_mismatch_fails_freeze(tmp_path: Path) -> None:
    from tests.test_public_history_dataset import _default_equity_catalog

    from app.market.history.freeze import FreezeError

    catalog = _default_equity_catalog()
    original = catalog["equity:US:AAPL"]
    catalog["equity:US:AAPL"] = original.model_copy(
        update={"metadata": original.metadata.model_copy(update={"source": "fred"})}
    )
    with pytest.raises(FreezeError, match="provider metadata"):
        _freeze(tmp_path, history=FreezeHistory(catalog))


def test_series_source_symbol_mismatch_fails_snapshot() -> None:
    from app.market.history.snapshot import PublicSnapshotError

    catalog = _equity_catalog()
    original = catalog["equity:US:AAPL"]
    catalog["equity:US:AAPL"] = original.model_copy(
        update={"metadata": original.metadata.model_copy(update={"source_symbol": "MSFT"})}
    )
    with pytest.raises(PublicSnapshotError, match="provider metadata"):
        _build(_MONDAY, history=SnapshotHistory(catalog))


def test_swapped_snapshot_id_date_must_not_bind() -> None:
    from app.market.history.snapshot import (
        MismatchedPublicSnapshotIdentityError,
        bind_risk_run_to_saved_snapshot,
        persist_public_snapshot,
    )

    built = _build(_MONDAY)
    swapped = built.snapshot.model_copy(update={"id": "real:public:wave-a:2024-01-12"})
    assert swapped.as_of == _MONDAY
    assert swapped.id != f"real:public:wave-a:{_MONDAY.isoformat()}"
    markets = InMemoryMarketSnapshotRepository()
    runs = InMemoryRiskRunRepository()
    with pytest.raises(MismatchedPublicSnapshotIdentityError):
        persist_public_snapshot(markets, built.__class__(snapshot=swapped, lineage=built.lineage))
    markets.save(swapped, meta=built.lineage)
    with pytest.raises(MismatchedPublicSnapshotIdentityError):
        bind_risk_run_to_saved_snapshot(
            run_repo=runs,
            market_repo=markets,
            run=RiskRun(id="run-swapped", portfolio_id="book-cash"),
            snapshot_id=swapped.id,
        )
    assert runs.get("run-swapped") is None


def test_freeze_then_adapters_unloaded_same_riskrun_lineage_and_numbers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.market.history.artifact import PUBLIC_HISTORY_CSV_ENV
    from app.market.history.snapshot import bind_risk_run_to_saved_snapshot, persist_public_snapshot
    from app.market.history.spec import WAVE_A_DATASET_ID
    from app.pricing.builtin import BuiltinPricingEngine
    from app.risk.historical_data import create_historical_dataset
    from app.services.risk_factories import build_historical_risk_engine, dataset_identity

    artifact = _freeze(tmp_path, history=FreezeHistory(), macro=FreezeMacro())
    built = _build(_MONDAY, history=SnapshotHistory(), macro=SnapshotMacro())
    markets = InMemoryMarketSnapshotRepository()
    runs = InMemoryRiskRunRepository()
    snapshot_id = persist_public_snapshot(markets, built)
    first_run = bind_risk_run_to_saved_snapshot(
        run_repo=runs,
        market_repo=markets,
        run=RiskRun(id="run-repro-1", portfolio_id="book-cash"),
        snapshot_id=snapshot_id,
    )
    monkeypatch.setenv(PUBLIC_HISTORY_CSV_ENV, str(artifact.csv_path))
    monkeypatch.delenv("QUANTLINEAGE_HISTORICAL_DATASET", raising=False)
    engine = BuiltinPricingEngine()
    book = _cash_book()
    first_vals = {item.position_id: item.market_value for item in engine.value_portfolio(book, built.snapshot)}
    hist = build_historical_risk_engine(historical_dataset_id=WAVE_A_DATASET_ID)
    first_id, first_version = dataset_identity(hist.dataset)
    first_summary = hist.calculate(book, engine, market=built.snapshot)

    def _http_forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("HTTP must not run after freeze")

    monkeypatch.setattr(httpx.Client, "request", _http_forbidden)
    monkeypatch.setattr(httpx.Client, "send", _http_forbidden)
    _drop_adapter_modules()
    assert "app.market.ingestion.yahoo" not in sys.modules
    assert "app.market.ingestion.fred" not in sys.modules

    dataset = create_historical_dataset(WAVE_A_DATASET_ID)
    rebound = build_historical_risk_engine(historical_dataset_id=WAVE_A_DATASET_ID)
    second_id, second_version = dataset_identity(rebound.dataset)
    loaded = markets.get(snapshot_id)
    assert loaded is not None
    second_run = bind_risk_run_to_saved_snapshot(
        run_repo=runs,
        market_repo=markets,
        run=RiskRun(id="run-repro-2", portfolio_id="book-cash"),
        snapshot_id=snapshot_id,
    )
    second_vals = {item.position_id: item.market_value for item in engine.value_portfolio(book, loaded)}
    second_summary = rebound.calculate(book, engine, market=loaded)

    assert dataset.dataset_id == WAVE_A_DATASET_ID == artifact.dataset_id
    assert first_id == second_id == artifact.dataset_id
    assert first_version == second_version == artifact.dataset_version
    assert first_run.market_snapshot_id == second_run.market_snapshot_id == built.snapshot.id
    assert loaded.id == built.snapshot.id
    assert loaded.content_hash() == built.snapshot.content_hash()
    assert first_vals == second_vals
    assert first_vals["eq-aapl"] == pytest.approx(10.0 * 185.0)
    assert first_summary.market_value == pytest.approx(second_summary.market_value)
    assert first_summary.var_95 == pytest.approx(second_summary.var_95)
    assert first_summary.var_99 == pytest.approx(second_summary.var_99)
    assert first_summary.expected_shortfall_99 == pytest.approx(second_summary.expected_shortfall_99)


def test_ci_workflows_stay_offline() -> None:
    forbidden = (
        "--live",
        "QUANTLINEAGE_DATA_MODE=public",
        "FRED_API_KEY",
        "query1.finance.yahoo.com",
        "api.stlouisfed.org",
    )
    for name in ("ci.yml", "nightly.yml"):
        text = (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
        jobs = text.split("\njobs:", 1)[-1]
        env_and_steps = []
        for line in jobs.splitlines():
            stripped = line.split("#", 1)[0]
            if "env:" in stripped or stripped.strip().startswith("run:") or "run: |" in stripped or (env_and_steps and stripped.startswith("          ")):
                env_and_steps.append(stripped)
        blob = "\n".join(env_and_steps) if env_and_steps else jobs
        for token in forbidden:
            assert token not in blob, f"{name} job env/steps contain {token!r}"
            assert token not in jobs, f"{name} jobs contain {token!r}"


def test_yahoo_and_fred_bases_are_hardcoded_module_constants() -> None:
    from app.market.ingestion.fred import FRED_BASE, FredAdapter
    from app.market.ingestion.yahoo import YAHOO_BASE, YahooFinanceAdapter

    assert YAHOO_BASE == "https://query1.finance.yahoo.com"
    assert FRED_BASE == "https://api.stlouisfed.org"
    yahoo_params = inspect.signature(YahooFinanceAdapter.__init__).parameters
    fred_params = inspect.signature(FredAdapter.__init__).parameters
    for name in ("base_url", "base", "host", "endpoint", "yahoo_base", "fred_base"):
        assert name not in yahoo_params
        assert name not in fred_params
    yahoo_src = (APP_ROOT / "market" / "ingestion" / "yahoo.py").read_text(encoding="utf-8")
    fred_src = (APP_ROOT / "market" / "ingestion" / "fred.py").read_text(encoding="utf-8")
    assert "os.getenv" not in yahoo_src
    assert "os.environ" not in yahoo_src
    assert "YAHOO_BASE =" in yahoo_src
    assert "FRED_BASE =" in fred_src
    tree = ast.parse(fred_src)
    getenv_names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in {"getenv", "get"}:
            if (isinstance(func.value, ast.Name) and func.value.id == "os") or (
                isinstance(func.value, ast.Attribute)
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "os"
                and func.value.attr == "environ"
                and func.attr == "get"
            ):
                arg0 = node.args[0]
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                    getenv_names.add(arg0.value)
    assert getenv_names <= {"FRED_API_KEY"}


def test_fred_key_absent_from_403_freeze_snapshot_and_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.market.history.freeze import freeze_public_history
    from app.market.history.snapshot import build_public_snapshot

    monkeypatch.setenv("FRED_API_KEY", _SECRET)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"error_code": 403, "error_message": f"Invalid API Key {_SECRET}"},
        )

    adapter = _fred(handler)
    with pytest.raises(AuthorizationError) as freeze_exc:
        freeze_public_history(
            history_provider=FreezeHistory(),
            macro_provider=adapter,
            output_dir=tmp_path,
            spec=_wave_a_spec(),
        )
    with pytest.raises(AuthorizationError) as snap_exc:
        build_public_snapshot(
            as_of=_MONDAY,
            history_provider=SnapshotHistory(),
            macro_provider=adapter,
        )
    artifact = _freeze(tmp_path / "ok")
    sidecar = json.loads(artifact.sidecar_path.read_text(encoding="utf-8"))
    built = _build(_MONDAY)
    provenance = json.dumps({"sidecar": sidecar, "lineage": built.lineage}, default=str)
    for blob in (str(freeze_exc.value), repr(freeze_exc.value), str(snap_exc.value), repr(snap_exc.value), provenance):
        assert _SECRET not in blob
        assert "api_key=" not in blob.lower()


def test_public_paths_emit_no_fx_or_fred_vol_surface(tmp_path: Path) -> None:
    built = _build(_MONDAY)
    snapshot = built.snapshot
    assert dict(snapshot.fx_spots) == {}
    assert dict(snapshot.fx_vols) == {}
    assert dict(snapshot.equity_vols) == {}
    assert dict(snapshot.vol_surfaces) == {}
    assert dict(snapshot.ir_vols) == {}
    lineage_blob = json.dumps(built.lineage)
    assert "EURUSD" not in lineage_blob
    assert "FXSpot" not in lineage_blob
    assert "vol_surface" not in lineage_blob
    artifact = _freeze(tmp_path)
    header = artifact.csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert "FXSpot" not in header
    assert "EURUSD" not in header
    assert "Vol" not in header
    sidecar = json.dumps(json.loads(artifact.sidecar_path.read_text(encoding="utf-8")))
    assert "EURUSD" not in sidecar
    assert "EquityVol" not in sidecar
    assert "vol_surface" not in sidecar
    assert "FRED" in sidecar
    assert "DGS10" in sidecar
