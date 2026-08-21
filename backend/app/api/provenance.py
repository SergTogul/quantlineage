"""Stable RiskRun calculation-lineage payload (Stage 10.5).

Displayed lineage must equal persisted/executed run fields. Release SHA is
taken from ``RISKFORGE_RELEASE_SHA`` or ``git describe``; it is omitted rather
than faked. Secrets are never included.
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.models import RiskRun, as_of_wire

_FAKE_SHA = frozenset({"unknown", "dev", "local", "none", "n/a"})


def resolve_release_sha() -> str | None:
    """Return a real release identifier, or None. Never invent a placeholder."""
    env = os.environ.get("RISKFORGE_RELEASE_SHA", "").strip()
    if env:
        return None if env.lower() in _FAKE_SHA else env
    return _git_describe()


@lru_cache(maxsize=1)
def _git_describe() -> str | None:
    repo = Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(
            ["git", "describe", "--always", "--dirty"],
            cwd=repo,
            check=False,
            capture_output=True,
            text=True,
            timeout=1.5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    sha = (completed.stdout or "").strip()
    if not sha or sha.lower() in _FAKE_SHA:
        return None
    return sha


def provenance_from_risk_run(run: RiskRun, *, duration_seconds: float | None = None) -> dict[str, Any]:
    """Map persisted RiskRun fields into the stable provenance payload."""
    duration = duration_seconds if duration_seconds is not None else run.duration
    payload: dict[str, Any] = {
        "risk_run_id": run.id,
        "portfolio_id": run.portfolio_id,
        "portfolio_version": run.portfolio_version,
        "market_snapshot_id": run.market_snapshot_id,
        "as_of": as_of_wire(run.as_of) if run.as_of is not None else None,
        "historical_dataset_id": run.historical_dataset_id,
        "historical_dataset_version": run.historical_dataset_version,
        "pricing_engine_version": run.pricing_engine_version,
        "methodology": run.methodology.value if run.methodology is not None else None,
        "scenario_set": list(run.scenario_set),
        "scenario_set_version": None,
        "calculation_config": (
            run.calculation_config.model_dump(mode="json")
            if run.calculation_config is not None
            else None
        ),
        "duration_seconds": duration,
        "status": run.status.value if hasattr(run.status, "value") else str(run.status),
        "release_sha": resolve_release_sha(),
    }
    return payload
