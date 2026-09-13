"""G7: optional public-data demo (no live Yahoo/FRED)."""

from __future__ import annotations

import ast
import re
import sys
from datetime import date
from pathlib import Path

import pytest
from tests.test_public_history_dataset import (
    FakeHistoryProvider,
    FakeMacroProvider,
    _wave_a_spec,
)
from tests.test_public_market_snapshot import (
    FakeHistoryProvider as SnapshotHistoryProvider,
)
from tests.test_public_market_snapshot import (
    FakeMacroProvider as SnapshotMacroProvider,
)
from tests.test_public_market_snapshot import (
    _equity_catalog,
    _macro_catalog,
)

from app.market.ingestion.models import Frequency, HistoricalPoint, InstrumentRef, MacroSeriesRef
from app.risk.historical_data import DEMO_MULTI_FACTOR_DATASET_ID, create_historical_dataset

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = Path(__file__).resolve().parents[1] / "app"
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_public_demo_data.py"
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
PUBLIC_DEMO_DOC = REPO_ROOT / "docs" / "public_data_demo.md"
FORBIDDEN_ADAPTERS = frozenset(
    {
        "app.market.ingestion.yahoo",
        "app.market.ingestion.fred",
    }
)
_SHA256 = re.compile(r"\b[0-9a-f]{64}\b")
_FRIDAY = date(2024, 1, 5)
_MONDAY = date(2024, 1, 8)
_TUESDAY = date(2024, 1, 9)


def _import_targets(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _drop_adapter_modules() -> None:
    for name in list(sys.modules):
        if (
            name in FORBIDDEN_ADAPTERS
            or name.startswith("app.market.ingestion.yahoo")
            or name.startswith("app.market.ingestion.fred")
        ):
            sys.modules.pop(name, None)


class ExplodingHistoryProvider:
    def fetch_history(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("Yahoo/history adapter must not be called")


class ExplodingMacroProvider:
    def fetch_series(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("FRED adapter must not be called")


_PREFIX_DATES = (
    date(2023, 12, 28),
    date(2023, 12, 29),
    date(2024, 1, 2),
    date(2024, 1, 3),
)


def _prefixed(catalog: dict):
    out = {}
    for instrument_id, series in catalog.items():
        first = series.points[0].value
        extra = [
            HistoricalPoint(observation_date=day, value=first - (len(_PREFIX_DATES) - i))
            for i, day in enumerate(_PREFIX_DATES)
        ]
        out[instrument_id] = series.model_copy(update={"points": extra + list(series.points)})
    return out


def _t0_t1_providers() -> tuple[SnapshotHistoryProvider, SnapshotMacroProvider]:
    return (
        SnapshotHistoryProvider(_prefixed(_equity_catalog())),
        SnapshotMacroProvider(_prefixed(_macro_catalog())),
    )


def _run_script(argv: list[str], *, history, macro, capsys) -> str:
    from app.market.history.public_demo import main

    rc = main(argv, history_provider=history, macro_provider=macro)
    assert rc == 0
    return capsys.readouterr().out


def test_script_with_fakes_prints_dataset_id_version_snapshot_and_coverage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = _wave_a_spec()
    printed = _run_script(
        [
            "--output",
            str(tmp_path),
            "--start",
            spec.start.isoformat(),
            "--end",
            spec.end.isoformat(),
            "--as-of",
            spec.end.isoformat(),
        ],
        history=FakeHistoryProvider(),
        macro=FakeMacroProvider(),
        capsys=capsys,
    )
    assert "real:public:wave-a" in printed
    assert _SHA256.search(printed) is not None
    assert f"real:public:wave-a:{spec.end.isoformat()}" in printed
    assert spec.start.isoformat() in printed
    assert spec.end.isoformat() in printed
    csvs = list((tmp_path / "real-public-wave-a").glob("*.csv"))
    assert len(csvs) == 1
    csv_path = csvs[0]
    assert csv_path.is_file()
    assert csv_path.stem == _SHA256.search(printed).group(0)
    assert csv_path.resolve() != (REPO_ROOT / "data" / "real_public_wave_a.csv").resolve()
    assert not (tmp_path / "real_public_wave_a.csv").exists()
    assert SCRIPT_PATH.is_file()
    shim = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "app.market.history.public_demo" in shim
    assert "--live" in shim or "live" in shim


def test_explicit_synthetic_data_mode_keeps_demo_dataset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUANTLINEAGE_DATA_MODE", "synthetic")
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    monkeypatch.delenv("QUANTLINEAGE_PUBLIC_HISTORY_CSV", raising=False)
    _drop_adapter_modules()
    dataset = create_historical_dataset()
    assert dataset.dataset_id == DEMO_MULTI_FACTOR_DATASET_ID
    loaded = [name for name in FORBIDDEN_ADAPTERS if name in sys.modules]
    assert loaded == [], f"synthetic mode loaded adapters: {loaded}"


def test_default_data_mode_unset_does_not_import_or_call_yahoo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("QUANTLINEAGE_DATA_MODE", raising=False)
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    monkeypatch.delenv("QUANTLINEAGE_PUBLIC_HISTORY_CSV", raising=False)
    _drop_adapter_modules()
    dataset = create_historical_dataset()
    assert dataset.dataset_id == DEMO_MULTI_FACTOR_DATASET_ID
    loaded = [name for name in FORBIDDEN_ADAPTERS if name in sys.modules]
    assert loaded == [], f"default factory loaded adapters: {loaded}"
    historical = APP_ROOT / "risk" / "historical_data.py"
    data_mode = APP_ROOT / "market" / "history" / "data_mode.py"
    for path in (historical, data_mode):
        imported = _import_targets(path)
        hit = imported & FORBIDDEN_ADAPTERS
        assert not hit, f"{path.name} imports adapters: {sorted(hit)}"


def test_compose_file_does_not_set_public_data_mode() -> None:
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    assert "QUANTLINEAGE_DATA_MODE=public" not in text
    assert "QUANTLINEAGE_DATA_MODE: public" not in text
    assert "QUANTLINEAGE_DATA_MODE: \"public\"" not in text


def test_public_data_demo_doc_exists() -> None:
    assert PUBLIC_DEMO_DOC.is_file()
    text = PUBLIC_DEMO_DOC.read_text(encoding="utf-8")
    assert "FRED_API_KEY" in text
    assert "QUANTLINEAGE_DATA_MODE" in text
    assert "build_public_demo_data.py" in text
    assert "Public-data mode currently covers US equity spot and USD Treasury-rate factors." in text
    assert "FX and volatility remain outside the public-data Wave A universe." in text
    assert "real-public-wave-a" in text


def test_public_mode_missing_csv_fails_closed_mentions_freeze_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUANTLINEAGE_DATA_MODE", "public")
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    monkeypatch.delenv("QUANTLINEAGE_PUBLIC_HISTORY_CSV", raising=False)
    with pytest.raises(ValueError, match="build_public_demo_data") as exc:
        create_historical_dataset()
    message = str(exc.value)
    assert "http" not in message.lower()
    assert "yahoo" not in message.lower()


def test_public_mode_with_frozen_csv_loads_without_adapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    spec = _wave_a_spec()
    _run_script(
        [
            "--output",
            str(tmp_path),
            "--start",
            spec.start.isoformat(),
            "--end",
            spec.end.isoformat(),
            "--as-of",
            spec.end.isoformat(),
        ],
        history=FakeHistoryProvider(),
        macro=FakeMacroProvider(),
        capsys=capsys,
    )
    csvs = list((tmp_path / "real-public-wave-a").glob("*.csv"))
    assert len(csvs) == 1
    csv_path = csvs[0]
    monkeypatch.setenv("QUANTLINEAGE_DATA_MODE", "public")
    monkeypatch.setenv("QUANTLINEAGE_PUBLIC_HISTORY_CSV", str(csv_path))
    monkeypatch.delenv("RISKFORGE_HISTORICAL_DATASET", raising=False)
    _drop_adapter_modules()
    dataset = create_historical_dataset()
    assert dataset.dataset_id == "real:public:wave-a"
    loaded = [name for name in FORBIDDEN_ADAPTERS if name in sys.modules]
    assert loaded == []
    history = ExplodingHistoryProvider()
    macro = ExplodingMacroProvider()
    with pytest.raises(AssertionError):
        history.fetch_history(
            InstrumentRef(instrument_id="equity:US:AAPL", asset_type="equity", currency="USD"),
            start=spec.start,
            end=spec.end,
            frequency=Frequency.DAILY,
        )
    with pytest.raises(AssertionError):
        macro.fetch_series(
            MacroSeriesRef(instrument_id="macro:FRED:DGS10", series_id="DGS10", currency="USD"),
            start=spec.start,
            end=spec.end,
        )


def test_t0_t1_prints_two_snapshot_ids_with_friday_vs_as_of_lineage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    printed = _run_script(
        [
            "--output",
            str(tmp_path),
            "--t0",
            _MONDAY.isoformat(),
            "--t1",
            _TUESDAY.isoformat(),
        ],
        history=_t0_t1_providers()[0],
        macro=_t0_t1_providers()[1],
        capsys=capsys,
    )
    assert "real:public:wave-a:2024-01-08" in printed
    assert "real:public:wave-a:2024-01-09" in printed
    assert _FRIDAY.isoformat() in printed
    assert _MONDAY.isoformat() in printed
    assert "risk/runs/compare" in printed or "Why did my risk change" in printed


def test_script_without_live_flag_does_not_construct_adapters(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from app.market.history.public_demo import main

    _drop_adapter_modules()
    rc = main(["--as-of", "2024-01-08"])
    captured = capsys.readouterr()
    assert rc != 0
    assert "--live" in captured.err
    loaded = [name for name in FORBIDDEN_ADAPTERS if name in sys.modules]
    assert loaded == []
