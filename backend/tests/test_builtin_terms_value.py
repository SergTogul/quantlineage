"""R0.2 Phase B — Builtin value() prices from InstrumentTerms + snapshot only."""
from __future__ import annotations
import pytest
from pydantic import ValidationError
from app.domain.instrument_terms import EquityTerms, terms_from_position
from app.domain.models import EquityPosition, EuropeanOptionPosition, MarketSnapshot
from app.pricing.builtin import BuiltinPricingEngine

@pytest.fixture
def engine():
    return BuiltinPricingEngine()

def _equity(*, quantity: float=10.0) -> EquityPosition:
    return EquityPosition(type='equity', id='eq-terms', symbol='ABC', quantity=quantity)

def _option(*, strike: float=100.0, quantity: float=10.0) -> EuropeanOptionPosition:
    return EuropeanOptionPosition(type='european_option', id='opt-terms', symbol='ABC', quantity=quantity, strike=strike, maturity_years=1.0, option_type='call')

def _equity_market(*, spot: float=100.0) -> MarketSnapshot:
    return MarketSnapshot(id='eq-snap', as_of='t0', equity_spots={'ABC': spot}, rates={'USD': 0.03})

def _option_market(*, spot: float=100.0, vol: float=0.2) -> MarketSnapshot:
    return MarketSnapshot(id='opt-snap', as_of='t0', equity_spots={'ABC': spot}, equity_vols={'ABC': vol}, rates={'USD': 0.03}, dividend_yields={'ABC': 0.0})

def test_snapshot_spot_is_sole_equity_mark_authority(engine):
    market = _equity_market(spot=100.0)
    pos = _equity()
    assert terms_from_position(pos).quantity == 10.0
    assert engine.value(pos, market).market_value == pytest.approx(10.0 * 100.0)
    with pytest.raises(ValidationError) as exc:
        EquityPosition(type='equity', id='x', symbol='ABC', quantity=1.0, price=999.0)
    assert any(e.get('type') == 'extra_forbidden' for e in exc.value.errors())

def test_snapshot_vol_is_sole_option_mark_authority(engine):
    market = _option_market(spot=100.0, vol=0.2)
    pos = _option()
    snap_pv = engine.value(pos, market).market_value
    low_vol = engine.value(pos, _option_market(spot=100.0, vol=0.05)).market_value
    high_vol = engine.value(pos, _option_market(spot=100.0, vol=0.8)).market_value
    assert snap_pv != pytest.approx(low_vol, rel=1e-06)
    assert snap_pv != pytest.approx(high_vol, rel=1e-06)
    with pytest.raises(ValidationError) as exc:
        EuropeanOptionPosition(
            type='european_option',
            id='x',
            symbol='ABC',
            quantity=1.0,
            strike=100.0,
            maturity_years=1.0,
            option_type='call',
            vol=0.99,
        )
    assert any(e.get('type') == 'extra_forbidden' for e in exc.value.errors())

def test_terms_quantity_and_strike_change_snapshot_pv(engine):
    eq_market = _equity_market(spot=100.0)
    qty_10 = engine.value(_equity(quantity=10.0), eq_market).market_value
    qty_20 = engine.value(_equity(quantity=20.0), eq_market).market_value
    assert qty_20 == pytest.approx(2.0 * qty_10, rel=1e-12, abs=1e-09)
    opt_market = _option_market()
    k90 = engine.value(_option(strike=90.0), opt_market).market_value
    k110 = engine.value(_option(strike=110.0), opt_market).market_value
    assert k90 > k110

def test_value_uses_terms_quantity_not_dto_when_terms_diverge(engine, monkeypatch):
    real_terms = terms_from_position

    def doubled_quantity(position):
        terms = real_terms(position)
        if isinstance(terms, EquityTerms):
            return terms.model_copy(update={'quantity': terms.quantity * 2.0})
        return terms
    monkeypatch.setattr('app.domain.instrument_terms.terms_from_position', doubled_quantity)
    import app.pricing.builtin as builtin_mod
    if hasattr(builtin_mod, 'terms_from_position'):
        monkeypatch.setattr(builtin_mod, 'terms_from_position', doubled_quantity)
    position = _equity(quantity=10.0)
    market = _equity_market(spot=100.0)
    pv = engine.value(position, market).market_value
    assert pv == pytest.approx(20.0 * 100.0, rel=1e-12, abs=1e-09)
    assert position.quantity == 10.0
