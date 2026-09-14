"""Optional QUANTLINEAGE_DATA_MODE. Never imports Yahoo/FRED adapters."""

from __future__ import annotations

import os

QUANTLINEAGE_DATA_MODE_ENV = "QUANTLINEAGE_DATA_MODE"
DATA_MODE_SYNTHETIC = "synthetic"
DATA_MODE_PUBLIC = "public"
HISTORICAL_DATASET_ENV = "QUANTLINEAGE_HISTORICAL_DATASET"
PUBLIC_DATASET_PREFIX = "real:public:"


def data_source_label(dataset_id: str | None, dataset_version: str | None) -> str | None:
    """Stable UI identity for a dataset. Kind comes from catalog id, not the client."""
    ident = (dataset_id or "").strip()
    if not ident:
        return None
    version = (dataset_version or "").strip() or "—"
    kind = "Public EOD" if ident.startswith(PUBLIC_DATASET_PREFIX) else "Synthetic replay"
    return f"{kind} · {ident}/{version}"


def resolve_data_mode() -> str:
    """``synthetic`` when unset; ``public`` is explicit/optional."""
    raw = os.getenv(QUANTLINEAGE_DATA_MODE_ENV, "").strip().lower()
    if raw in {"", DATA_MODE_SYNTHETIC}:
        return DATA_MODE_SYNTHETIC
    if raw == DATA_MODE_PUBLIC:
        return DATA_MODE_PUBLIC
    raise ValueError(
        f"unknown {QUANTLINEAGE_DATA_MODE_ENV}={raw!r}; use {DATA_MODE_SYNTHETIC!r} or {DATA_MODE_PUBLIC!r}"
    )


def apply_quantlineage_data_mode(source: str | None) -> str:
    """Resolve factory source. Empty string means the synthetic demo default.

    Explicit ``source`` / ``QUANTLINEAGE_HISTORICAL_DATASET`` win. Public mode
    selects ``real:public:wave-a`` only when those are unset.
    """
    if source is not None and source.strip():
        return source.strip()
    env_dataset = os.getenv(HISTORICAL_DATASET_ENV, "").strip()
    if env_dataset:
        return env_dataset
    if resolve_data_mode() == DATA_MODE_PUBLIC:
        from app.market.history.spec import WAVE_A_DATASET_ID

        return WAVE_A_DATASET_ID
    return ""
