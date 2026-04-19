"""R0.5.2 — QuantLib production mode fails closed on unknown instruments.

Unknown / unhandled position types must raise from QuantLibPricingEngine.value
and must not delegate to BuiltinPricingEngine. Builtin remains available only
via the factory path (RISKFORGE_PRICING_ENGINE=builtin), which this slice
does not change.
"""

from datetime import date

import pytest
from tests.quantlib_gate import import_quantlib
from app.interfaces.pricing import LegacyDemoPricingAdapter

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
