"""QuantLib import helper: optional locally, mandatory in the full CI gate.

Set ``RISKFORGE_REQUIRE_QUANTLIB=1`` so a missing QuantLib install fails the
job instead of ``pytest.importorskip`` skipping to green (R0.1.6 / RF-016).
"""

from __future__ import annotations

import os

import pytest

_TRUTHY = {"1", "true", "yes", "on"}


def quantlib_required() -> bool:
    return os.environ.get("RISKFORGE_REQUIRE_QUANTLIB", "").strip().lower() in _TRUTHY


def import_quantlib():
    try:
        import QuantLib as ql
    except ImportError as exc:
        if quantlib_required():
            raise RuntimeError(
                "QuantLib is required (RISKFORGE_REQUIRE_QUANTLIB=1) but could not "
                "be imported. Install backend/requirements.txt including QuantLib."
            ) from exc
        pytest.skip("QuantLib is not installed", allow_module_level=True)
    return ql
