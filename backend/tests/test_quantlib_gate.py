"""R0.1.6 — QuantLib hard-gate helper."""

from __future__ import annotations

from tests.quantlib_gate import import_quantlib, quantlib_required


def test_import_quantlib_returns_installed_module():
    ql = import_quantlib()
    assert hasattr(ql, "Date")
    assert hasattr(ql, "Settings")


def test_quantlib_required_reads_env(monkeypatch):
    monkeypatch.delenv("RISKFORGE_REQUIRE_QUANTLIB", raising=False)
    assert quantlib_required() is False
    monkeypatch.setenv("RISKFORGE_REQUIRE_QUANTLIB", "1")
    assert quantlib_required() is True
    monkeypatch.setenv("RISKFORGE_REQUIRE_QUANTLIB", "true")
    assert quantlib_required() is True
