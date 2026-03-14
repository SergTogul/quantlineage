"""QuantLib import helper: optional locally, mandatory in the full CI gate.

Set ``RISKFORGE_REQUIRE_QUANTLIB=1`` so a missing QuantLib install fails the
job instead of ``pytest.importorskip`` skipping to green (R0.1.6 / RF-016).

``require_quantlib_for_nightly`` fail-closes when ``RISKFORGE_NIGHTLY=1`` so
the nightly QuantLib E2E job cannot skip-green if the wheel is missing.
"""

from __future__ import annotations

import os

import pytest

_TRUTHY = {"1", "true", "yes", "on"}


def quantlib_required() -> bool:
    return os.environ.get("RISKFORGE_REQUIRE_QUANTLIB", "").strip().lower() in _TRUTHY


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _import_quantlib_module():
    import QuantLib as ql

    return ql


def import_quantlib():
    try:
        return _import_quantlib_module()
    except ImportError as exc:
        if quantlib_required():
            raise RuntimeError(
                "QuantLib is required (RISKFORGE_REQUIRE_QUANTLIB=1) but could not "
                "be imported. Install backend/requirements.txt including QuantLib."
            ) from exc
        pytest.skip("QuantLib is not installed", allow_module_level=True)


def require_quantlib_for_nightly(*, _importer=None):
    """Import QuantLib, or fail/skip.

    * ``RISKFORGE_NIGHTLY`` set: **fail** if QuantLib cannot be imported
      (nightly QuantLib E2E; no skip-green).
    * ``RISKFORGE_REQUIRE_QUANTLIB`` set: **fail** (same intent as the hard-gate).
    * Otherwise: skip if missing (local optional).
    """
    importer = _importer or _import_quantlib_module
    try:
        return importer()
    except ImportError:
        if _env_flag("RISKFORGE_NIGHTLY") or quantlib_required():
            pytest.fail(
                "QuantLib must be importable when RISKFORGE_NIGHTLY=1 or "
                "RISKFORGE_REQUIRE_QUANTLIB=1 (no skip-green)"
            )
        pytest.skip("QuantLib is not installed")
