"""R0.5.2 — QuantLib production mode fails closed on unknown instruments.

Unknown / unhandled position types must raise from QuantLibPricingEngine.value
and must not delegate to BuiltinPricingEngine. Builtin remains available only
via the factory path (QUANTLINEAGE_PRICING_ENGINE=builtin), which this slice
does not change.
"""

from datetime import date

import pytest
from tests.quantlib_gate import import_quantlib

ql = import_quantlib()

from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.quantlib import QuantLibPricingEngine


class _UnknownPosition:
    """Dummy type that is not in the QuantLib isinstance chain."""

    id = "mystery"
    type = "mystery"


def _forbid_builtin_fallback(monkeypatch):
    def boom(self, position, market=None):
        raise AssertionError(
            f"QuantLibPricingEngine must not fall back to Builtin for {type(position).__name__}"
        )

    monkeypatch.setattr(BuiltinPricingEngine, "value", boom)


@pytest.fixture
def engine():
    return QuantLibPricingEngine(evaluation_date=date(2026, 9, 1))


def test_unknown_instrument_raises_without_builtin_fallback(engine, monkeypatch):
    _forbid_builtin_fallback(monkeypatch)

    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        engine.value(_UnknownPosition())  # type: ignore[arg-type]


def test_unknown_instrument_raises_when_market_is_supplied(engine, monkeypatch):
    from app.domain.models import MarketSnapshot

    _forbid_builtin_fallback(monkeypatch)
    market = MarketSnapshot(id="m", as_of="t0", equity_spots={}, rates={})

    with pytest.raises(TypeError, match="unsupported instrument") as excinfo:
        engine.value(_UnknownPosition(), market)  # type: ignore[arg-type]

    message = str(excinfo.value)
    assert "QuantLib" in message
    assert "_UnknownPosition" in message


def test_quantlib_value_consults_get_capability(engine, monkeypatch):
    from app.domain.models import EquityPosition, MarketSnapshot

    _forbid_builtin_fallback(monkeypatch)
    monkeypatch.setattr(
        "app.pricing.quantlib.get_capability",
        lambda family: (_ for _ in ()).throw(AssertionError(f"wired:{family}")),
        raising=False,
    )
    position = EquityPosition(type="equity", id="e", symbol="ABC", quantity=1)
    market = MarketSnapshot(id="m", equity_spots={"ABC": 10.0}, rates={"USD": 0.04})
    with pytest.raises(AssertionError, match="wired:equity"):
        engine.value(position, market)


def test_quantlib_snapshot_overlay_unknown_family_fails_closed(monkeypatch):
    from app.domain.models import MarketSnapshot
    from app.pricing.snapshot_overlay import snapshot_marks_from_terms

    _forbid_builtin_fallback(monkeypatch)

    class _UnknownTerms:
        type = "convertible_bond"
        id = "mystery"

    market = MarketSnapshot(id="m", as_of="t0", equity_spots={}, rates={})
    with pytest.raises((KeyError, TypeError), match="unknown instrument family"):
        snapshot_marks_from_terms(_UnknownTerms(), market)  # type: ignore[arg-type]


def test_quantlib_unregistered_terms_fail_closed_without_builtin(engine, monkeypatch):
    from app.domain.models import MarketSnapshot

    class _UnknownTerms:
        type = "convertible_bond"
        id = "mystery"

        def model_dump(self):
            return {"type": self.type, "id": self.id}

    _forbid_builtin_fallback(monkeypatch)
    monkeypatch.setattr(engine, "_terms_for_position", lambda position: _UnknownTerms())
    market = MarketSnapshot(id="m", as_of="t0", equity_spots={}, rates={})
    with pytest.raises((KeyError, TypeError), match="unknown instrument family"):
        engine.value(_UnknownPosition(), market)  # type: ignore[arg-type]
