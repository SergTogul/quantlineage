"""Optional public-data demo freeze + snapshot. Tests inject fakes; ``--live`` is opt-in."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path

from app.market.history.artifact import PUBLIC_HISTORY_CSV_NAME
from app.market.history.freeze import FrozenHistoryArtifact, freeze_public_history
from app.market.history.snapshot import PublicSnapshotBuild, build_public_snapshot
from app.market.history.spec import WAVE_A_FACTOR_MAPPINGS, WAVE_A_SPEC, PublicHistoryDatasetSpec
from app.market.ingestion.protocols import HistoricalDataProvider, MacroDataProvider

COMPARE_HINT = (
    "To compare T0 vs T1 risk, persist two COMPLETED RiskRuns bound to these snapshot ids "
    "and use existing POST /api/v1/risk/runs/compare (Analytics: Why did my risk change?). "
    "This script does not invent a compare engine."
)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Materialize optional public Wave A history (Yahoo public EOD + FRED). "
            "Default does not fetch. Pass --live for public HTTP."
        )
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch from Yahoo/FRED adapters (never used in CI/tests)",
    )
    parser.add_argument(
        "--output",
        help=(
            "Directory or CSV path for the freeze artifact. "
            f"Writes {PUBLIC_HISTORY_CSV_NAME}. Omit to use a temp directory."
        ),
    )
    parser.add_argument("--start", type=_parse_date, default=WAVE_A_SPEC.start)
    parser.add_argument("--end", type=_parse_date, default=WAVE_A_SPEC.end)
    parser.add_argument("--as-of", dest="as_of", type=_parse_date, default=None)
    parser.add_argument("--t0", type=_parse_date, default=None)
    parser.add_argument("--t1", type=_parse_date, default=None)
    return parser.parse_args(argv)


def output_dir_for(output: str | None) -> Path:
    if not output:
        return Path(tempfile.mkdtemp(prefix="quantlineage-public-"))
    path = Path(output).expanduser()
    if path.suffix.lower() == ".csv":
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.parent.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _aligned_observation_count(csv_path: Path) -> int:
    lines = [line for line in csv_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return max(0, len(lines) - 1)


def _warnings_from_sidecar(payload: dict) -> list[str]:
    warnings: list[str] = []
    dropped = payload.get("dropped_dates") or {}
    if isinstance(dropped, dict):
        for instrument_id, days in dropped.items():
            if days:
                warnings.append(f"dropped {instrument_id} {','.join(days)}")
    return warnings


def _source_symbols() -> str:
    return ",".join(item.source_symbol for item in WAVE_A_FACTOR_MAPPINGS)


def _source_observation_dates(built: PublicSnapshotBuild) -> str:
    marks = built.lineage.get("marks") or {}
    dates: list[str] = []
    for mark in marks.values():
        if not isinstance(mark, dict):
            continue
        day = mark.get("source_observation_date")
        if isinstance(day, str) and day and day not in dates:
            dates.append(day)
    return ",".join(dates)


def format_report(
    *,
    spec: PublicHistoryDatasetSpec,
    artifact: FrozenHistoryArtifact,
    aligned_observations: int,
    warnings: list[str],
    snapshots: list[tuple[str, PublicSnapshotBuild]],
) -> str:
    lines = [
        f"provider: {spec.provider_source}",
        f"source_symbols: {_source_symbols()}",
        f"coverage: {spec.start.isoformat()}/{spec.end.isoformat()}",
        f"aligned_observations: {aligned_observations}",
        f"dataset_id: {artifact.dataset_id}",
        f"dataset_version: {artifact.dataset_version}",
        f"dataset_hash: {artifact.dataset_version}",
    ]
    for label, built in snapshots:
        prefix = f"{label}_" if label not in {"", "snapshot"} else ""
        if label in {"", "snapshot"}:
            lines.append(f"snapshot_id: {built.snapshot.id}")
            lines.append(f"snapshot_as_of: {built.snapshot.as_of.isoformat()}")
            lines.append(f"source_observation_date: {_source_observation_dates(built)}")
        else:
            lines.append(f"{prefix}snapshot_id: {built.snapshot.id}")
            lines.append(f"{prefix}as_of: {built.snapshot.as_of.isoformat()}")
            lines.append(
                f"{prefix}source_observation_date: {_source_observation_dates(built)}"
            )
    if warnings:
        lines.append("warnings: " + "; ".join(warnings))
    else:
        lines.append("warnings: none")
    labels = {label for label, _ in snapshots}
    if "t0" in labels and "t1" in labels:
        lines.append(COMPARE_HINT)
    return "\n".join(lines) + "\n"


def run_public_demo(
    *,
    history_provider: HistoricalDataProvider,
    macro_provider: MacroDataProvider,
    output_dir: str | Path,
    spec: PublicHistoryDatasetSpec = WAVE_A_SPEC,
    as_of: date | None = None,
    t0: date | None = None,
    t1: date | None = None,
) -> str:
    artifact = freeze_public_history(
        history_provider=history_provider,
        macro_provider=macro_provider,
        output_dir=output_dir,
        spec=spec,
    )
    sidecar = json.loads(artifact.sidecar_path.read_text(encoding="utf-8"))
    warnings = _warnings_from_sidecar(sidecar)
    aligned = _aligned_observation_count(artifact.csv_path)
    snapshots: list[tuple[str, PublicSnapshotBuild]] = []
    if as_of is not None:
        snapshots.append(
            (
                "snapshot",
                build_public_snapshot(
                    as_of=as_of,
                    history_provider=history_provider,
                    macro_provider=macro_provider,
                    spec=spec,
                ),
            )
        )
    if t0 is not None:
        snapshots.append(
            (
                "t0",
                build_public_snapshot(
                    as_of=t0,
                    history_provider=history_provider,
                    macro_provider=macro_provider,
                    spec=spec,
                ),
            )
        )
    if t1 is not None:
        snapshots.append(
            (
                "t1",
                build_public_snapshot(
                    as_of=t1,
                    history_provider=history_provider,
                    macro_provider=macro_provider,
                    spec=spec,
                ),
            )
        )
    if not snapshots:
        snapshots.append(
            (
                "snapshot",
                build_public_snapshot(
                    as_of=spec.end,
                    history_provider=history_provider,
                    macro_provider=macro_provider,
                    spec=spec,
                ),
            )
        )
    return format_report(
        spec=spec,
        artifact=artifact,
        aligned_observations=aligned,
        warnings=warnings,
        snapshots=snapshots,
    )


def main(
    argv: list[str] | None = None,
    *,
    history_provider: HistoricalDataProvider | None = None,
    macro_provider: MacroDataProvider | None = None,
) -> int:
    args = parse_args(argv)
    if history_provider is None or macro_provider is None:
        print(
            "error: public fetch is opt-in; pass --live to use Yahoo/FRED adapters "
            "(tests inject fakes; CI must not fetch)",
            file=sys.stderr,
        )
        return 2
    spec = replace(WAVE_A_SPEC, start=args.start, end=args.end)
    printed = run_public_demo(
        history_provider=history_provider,
        macro_provider=macro_provider,
        output_dir=output_dir_for(args.output),
        spec=spec,
        as_of=args.as_of,
        t0=args.t0,
        t1=args.t1,
    )
    sys.stdout.write(printed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
