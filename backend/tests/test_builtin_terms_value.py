"""R0.2 leftover — Builtin value() prices from InstrumentTerms + snapshot.

Economics identity is ``terms_from_position``. Leftover ``*Position`` DTO
marks are not an authority when an explicit ``MarketSnapshot`` is supplied.
"""

from __future__ import annotations

import pytest

from app.domain.instrument_terms import EquityTerms, terms_from_position
from app.domain.models import EquityPosition, EuropeanOptionPosition, MarketSnapshot
from app.pricing.builtin import BuiltinPricingEngine
from app.interfaces.pricing import LegacyDemoPricingAdapter


@pytest.fixture
def engine():
    return BuiltinPricingEngine()


def _equity(*, price: float, quantity: float = 10.0) -> EquityPosition:
    return EquityPosition(
        type="equity",
        id="eq-terms",
        symbol="ABC",
        quantity=quantity,
        price=price,
    )


def _option(
    *,
    spot: float,
    strike: float = 100.0,
    quantity: float = 10.0,
    volatility: float = 0.20,
) -> EuropeanOptionPosition:
    return EuropeanOptionPosition(
        type="european_option",
        id="opt-terms",
        symbol="ABC",
        quantity=quantity,
        spot=spot,
        strike=strike,
        maturity_years=1.0,
        volatility=volatility,
        risk_free_rate=0.03,
        dividend_yield=0.0,
        option_type="call",
    )


def _equity_market(*, spot: float = 100.0) -> MarketSnapshot:
    return MarketSnapshot(
        id="eq-snap",
        as_of="t0",
        equity_spots={"ABC": spot},
        rates={"USD": 0.03},
    )


def _option_market(*, spot: float = 100.0, vol: float = 0.20) -> MarketSnapshot:
    return MarketSnapshot(
        id="opt-snap",
        as_of="t0",
        equity_spots={"ABC": spot},
        equity_vols={"ABC": vol},
        rates={"USD": 0.03},
        dividend_yields={"ABC": 0.0},
    )


def test_dto_mark_divergence_does_not_change_snapshot_equity_pv(engine):
    """Two cash equities that differ only in leftover DTO price still match."""
    market = _equity_market(spot=100.0)
    cheap = _equity(price=1.0)
    rich = _equity(price=999.0)
    assert cheap.price != rich.price
    assert terms_from_position(cheap) == terms_from_position(rich)

    cheap_pv = engine.value(cheap, market).market_value
    rich_pv = engine.value(rich, market).market_value
    assert cheap_pv == pytest.approx(rich_pv, rel=1e-12, abs=1e-9)
    assert cheap_pv == pytest.approx(10.0 * 100.0, rel=1e-12, abs=1e-9)
    assert cheap.price == 1.0
    assert rich.price == 999.0


def test_dto_mark_divergence_does_not_change_snapshot_option_pv(engine):
    """Leftover option spot/vol on the DTO must not win over the snapshot."""
    market = _option_market(spot=100.0, vol=0.20)
    low = _option(spot=40.0, volatility=0.05)
    high = _option(spot=180.0, volatility=0.80)
    assert terms_from_position(low) == terms_from_position(high)

    low_pv = engine.value(low, market).market_value
    high_pv = engine.value(high, market).market_value
    assert low_pv == pytest.approx(high_pv, rel=1e-12, abs=1e-9)
    # Snapshot ATM 20% vol is not the leftover 5% or 80% DTO marks.
    assert low_pv != pytest.approx(LegacyDemoPricingAdapter(engine).value(low).market_value, rel=1e-6)
    assert high_pv != pytest.approx(LegacyDemoPricingAdapter(engine).value(high).market_value, rel=1e-6)


def test_terms_quantity_and_strike_change_snapshot_pv(engine):
    """Contractual quantity and strike still move PV after terms wiring."""
    eq_market = _equity_market(spot=100.0)
    qty_10 = engine.value(_equity(price=1.0, quantity=10.0), eq_market).market_value
    qty_20 = engine.value(_equity(price=1.0, quantity=20.0), eq_market).market_value
    assert qty_20 == pytest.approx(2.0 * qty_10, rel=1e-12, abs=1e-9)

    opt_market = _option_market()
    k90 = engine.value(_option(spot=1.0, strike=90.0), opt_market).market_value
    k110 = engine.value(_option(spot=1.0, strike=110.0), opt_market).market_value
    assert k90 > k110


def test_value_uses_terms_quantity_not_dto_when_terms_diverge(engine, monkeypatch):
    """Economics identity is terms_from_position, not the leftover DTO quantity."""
    real_terms = terms_from_position

    def doubled_quantity(position):
        terms = real_terms(position)
        if isinstance(terms, EquityTerms):
            return terms.model_copy(update={"quantity": terms.quantity * 2.0})
        return terms

    # Patch the domain symbol so value() must call terms_from_position
    # (a local ``from … import`` binding is also patched below if present).
    monkeypatch.setattr(
        "app.domain.instrument_terms.terms_from_position", doubled_quantity
    )
    import app.pricing.builtin as builtin_mod

    if hasattr(builtin_mod, "terms_from_position"):
        monkeypatch.setattr(builtin_mod, "terms_from_position", doubled_quantity)

    position = _equity(price=1.0, quantity=10.0)
    market = _equity_market(spot=100.0)
    pv = engine.value(position, market).market_value
    assert pv == pytest.approx(20.0 * 100.0, rel=1e-12, abs=1e-9)
    assert position.quantity == 10.0
