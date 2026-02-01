"""Deterministic demo helpers (Milestone 10)."""

from __future__ import annotations

from typing import Any

__all__ = [
    "DEMO_ARTIFACT_SCHEMA_VERSION",
    "build_demo_risk_artifact",
    "dumps_demo_artifact",
    "run_demo_risk",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from app.demo import run_demo_risk as _mod

        return getattr(_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
