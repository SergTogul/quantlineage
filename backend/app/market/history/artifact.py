"""Frozen public-history CSV + sidecar paths. No providers, no HTTP."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

PUBLIC_HISTORY_CSV_ENV = "QUANTLINEAGE_PUBLIC_HISTORY_CSV"
PUBLIC_HISTORY_DIR_ENV = "QUANTLINEAGE_PUBLIC_HISTORY_DIR"
PUBLIC_HISTORY_DATASET_SLUG = "real-public-wave-a"
_SHA256_HEX_LEN = 64
_HEX_DIGITS = frozenset("0123456789abcdef")

# Legacy singleton name kept for fail-closed messages pointing at old docs/env pins.
PUBLIC_HISTORY_CSV_NAME = "real_public_wave_a.csv"


def _repo_root() -> Path:
    # backend/app/market/history/artifact.py → parents[4] = repo root
    return Path(__file__).resolve().parents[4]


def default_public_history_dir() -> Path:
    return _repo_root() / "data" / "public_history" / PUBLIC_HISTORY_DATASET_SLUG


def default_public_history_csv_path() -> Path:
    """Default versioned dataset directory (not a singleton CSV)."""
    return default_public_history_dir()


def public_history_dataset_dir(output_dir: str | Path) -> Path:
    """Map a freeze output root onto ``…/real-public-wave-a``."""
    path = Path(output_dir).expanduser()
    if path.name == PUBLIC_HISTORY_DATASET_SLUG:
        return path
    return path / PUBLIC_HISTORY_DATASET_SLUG


def is_content_hash(value: str) -> bool:
    digest = value.strip().lower()
    return len(digest) == _SHA256_HEX_LEN and all(char in _HEX_DIGITS for char in digest)


def versioned_csv_path(dataset_dir: str | Path, dataset_version: str) -> Path:
    digest = dataset_version.strip().lower()
    if not is_content_hash(digest):
        raise ValueError(f"invalid public history dataset_version: {dataset_version!r}")
    return Path(dataset_dir) / f"{digest}.csv"


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


def _missing_csv_message(path: Path | None = None) -> str:
    where = f": {path}" if path is not None else ""
    return (
        f"frozen public history CSV not found{where}; "
        "run python scripts/build_public_demo_data.py "
        "(see docs/public_data_demo.md)"
    )


def _is_versioned_csv(path: Path) -> bool:
    return path.suffix.lower() == ".csv" and is_content_hash(path.stem)


def list_versioned_csvs(dataset_dir: Path) -> list[Path]:
    if not dataset_dir.is_dir():
        return []
    return sorted(path for path in dataset_dir.glob("*.csv") if _is_versioned_csv(path))


def _dataset_dir_from_env() -> Path:
    raw_dir = os.getenv(PUBLIC_HISTORY_DIR_ENV, "").strip()
    if raw_dir:
        return public_history_dataset_dir(Path(raw_dir).expanduser())
    raw_csv = os.getenv(PUBLIC_HISTORY_CSV_ENV, "").strip()
    if raw_csv:
        csv_path = Path(raw_csv).expanduser()
        parent = csv_path.parent if csv_path.suffix.lower() == ".csv" else csv_path
        return public_history_dataset_dir(parent)
    return default_public_history_dir()


def resolve_public_history_csv(*, dataset_version: str | None = None) -> Path:
    """Locate a frozen Wave A CSV. Never fetches; fail closed if missing.

    ``dataset_id`` (``real:public:wave-a``) plus ``dataset_version`` (content hash)
    resolve immutable bytes. A pinned ``QUANTLINEAGE_PUBLIC_HISTORY_CSV`` still
    selects that file when version is omitted.
    """
    requested = dataset_version.strip().lower() if dataset_version else None
    if requested is not None and not is_content_hash(requested):
        raise ValueError(f"invalid public history dataset_version: {dataset_version!r}")

    dataset_dir = _dataset_dir_from_env()
    if requested is not None:
        hashed = versioned_csv_path(dataset_dir, requested)
        if hashed.is_file():
            return hashed.resolve()
        pinned = os.getenv(PUBLIC_HISTORY_CSV_ENV, "").strip()
        if pinned:
            pinned_path = Path(pinned).expanduser()
            if pinned_path.is_file() and pinned_path.stem.lower() == requested:
                return pinned_path.resolve()
        raise ValueError(_missing_csv_message(hashed))

    pinned = os.getenv(PUBLIC_HISTORY_CSV_ENV, "").strip()
    if pinned:
        path = Path(pinned).expanduser()
        if not path.is_file():
            raise ValueError(_missing_csv_message(path))
        return path.resolve()

    found = list_versioned_csvs(dataset_dir)
    if len(found) == 1:
        return found[0].resolve()
    if len(found) > 1:
        return max(found, key=lambda path: path.stat().st_mtime).resolve()
    raise ValueError(
        "frozen public history CSV not found; run python scripts/build_public_demo_data.py "
        f"(see docs/public_data_demo.md) or set {PUBLIC_HISTORY_CSV_ENV} "
        f"or {PUBLIC_HISTORY_DIR_ENV} or place hashed CSVs under "
        f"data/public_history/{PUBLIC_HISTORY_DATASET_SLUG}/"
    )
