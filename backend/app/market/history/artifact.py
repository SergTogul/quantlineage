"""Frozen public-history CSV + sidecar paths. No providers, no HTTP."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

PUBLIC_HISTORY_CSV_ENV = "QUANTLINEAGE_PUBLIC_HISTORY_CSV"
PUBLIC_HISTORY_CSV_NAME = "real_public_wave_a.csv"


def _repo_root() -> Path:
    # backend/app/market/history/artifact.py → parents[4] = repo root
    return Path(__file__).resolve().parents[4]


def default_public_history_csv_path() -> Path:
    return _repo_root() / "data" / PUBLIC_HISTORY_CSV_NAME


def sidecar_path_for_csv(csv_path: str | Path) -> Path:
    return Path(csv_path).expanduser().resolve().with_suffix(".json")


def sidecar_identity(csv_path: str | Path) -> tuple[str | None, str | None]:
    """Return ``(dataset_id, dataset_version)`` from a sidecar, if present."""
    path = sidecar_path_for_csv(csv_path)
    if not path.is_file():
        return None, None
    payload = json.loads(path.read_text(encoding="utf-8"))
    dataset_id = payload.get("dataset_id")
    dataset_version = payload.get("dataset_version")
    resolved_id = dataset_id.strip() if isinstance(dataset_id, str) and dataset_id.strip() else None
    resolved_version = (
        dataset_version.strip()
        if isinstance(dataset_version, str) and dataset_version.strip()
        else None
    )
    return resolved_id, resolved_version


def write_sidecar(path: str | Path, payload: Mapping[str, Any]) -> Path:
    sidecar = Path(path)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return sidecar


def resolve_public_history_csv() -> Path:
    """Locate the frozen Wave A CSV. Never fetches; fail closed if missing."""
    raw = os.getenv(PUBLIC_HISTORY_CSV_ENV, "").strip()
    if raw:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise ValueError(
                f"frozen public history CSV not found: {path}; "
                "run python scripts/build_public_demo_data.py "
                "(see docs/public_data_demo.md)"
            )
        return path.resolve()
    default = default_public_history_csv_path()
    if default.is_file():
        return default.resolve()
    raise ValueError(
        "frozen public history CSV not found; run python scripts/build_public_demo_data.py "
        f"(see docs/public_data_demo.md) or set {PUBLIC_HISTORY_CSV_ENV} "
        f"or place {PUBLIC_HISTORY_CSV_NAME} under data/"
    )
