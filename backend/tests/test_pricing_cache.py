"""Correctness tests for CachedPricingEngine (M5.5).

Units: currency market_value matching BuiltinPricingEngine.
Invariant: cache hit returns equal Valuation; market bump / trade / config change → miss.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.models import (
    BondPosition,
    CapFloorPosition,
    EquityFuturePosition,
    EquityPosition,
    EuropeanOptionPosition,
    FXForwardPosition,
    FXOptionPosition,
    InterestRateFuturePosition,
    MarketSnapshot,
    SwapPosition,
    SwaptionPosition,
    Valuation,
)
from app.interfaces.pricing import PricingEngine
from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.cache import (
    CachedPricingEngine,
    PricingConfiguration,
    market_cache_key,
    trade_cache_key,
    valuation_cache_key,
)
from app.risk.factor_types import EquitySpot


class CountingPricingEngine(PricingEngine):
    """Delegates to Builtin while counting ``value`` invocations."""

    def __init__(self) -> None:
        self.calls = 0
        self._inner = BuiltinPricingEngine()

    def value(self, position, market=None) -> Valuation:
        self.calls += 1
        return self._inner.value(position, market)


def _equity() -> EquityPosition:
    return EquityPosition(type="equity", id="eq1", symbol="SPY", quantity=10)


def _market(spot: float = 100.0) -> MarketSnapshot:
    return MarketSnapshot(id="m1", as_of="t0", equity_spots={"SPY": spot}, rates={"USD": 0.04})


def test_trade_and_market_keys_stable():
    p = _equity()
    m = _market()
    assert trade_cache_key(p) == trade_cache_key(p.model_copy())
    # Labels stay equivalent; id is excluded. Parseable ISO as_of is not a label.
    labeled_other_id = MarketSnapshot(
        id="other", as_of="t0", equity_spots={"SPY": 100.0}, rates={"USD": 0.04}
    )
    labeled_current = MarketSnapshot(
        id="third", as_of="current", equity_spots={"SPY": 100.0}, rates={"USD": 0.04}
    )
    iso_2018 = MarketSnapshot(
        id="iso-a", as_of="2018-01-01", equity_spots={"SPY": 100.0}, rates={"USD": 0.04}
    )
    iso_2018_other_id = MarketSnapshot(
        id="iso-b", as_of="2018-01-01", equity_spots={"SPY": 100.0}, rates={"USD": 0.04}
    )
    iso_2024 = MarketSnapshot(
        id="iso-c", as_of="2024-06-14", equity_spots={"SPY": 100.0}, rates={"USD": 0.04}
    )
    assert market_cache_key(m) == market_cache_key(labeled_other_id)
    assert market_cache_key(m) == market_cache_key(labeled_current)
    assert market_cache_key(iso_2018) == market_cache_key(iso_2018_other_id)
    assert market_cache_key(iso_2018) != market_cache_key(iso_2024)
    assert market_cache_key(iso_2018) != market_cache_key(m)
    date_2018 = MarketSnapshot.model_construct(
        id="iso-date",
        as_of=date(2018, 1, 1),
        equity_spots={"SPY": 100.0},
        rates={"USD": 0.04},
    )
    assert market_cache_key(date_2018) == market_cache_key(iso_2018)
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        market_cache_key(None)


def test_cache_miss_on_parseable_as_of_change():
    """ISO as_of is load-bearing for valuation identity even when marks match."""
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    pos = _equity()
    m2018 = MarketSnapshot(
        id="a", as_of="2018-01-01", equity_spots={"SPY": 100.0}, rates={"USD": 0.04}
    )
    m2024 = MarketSnapshot(
        id="b", as_of="2024-06-14", equity_spots={"SPY": 100.0}, rates={"USD": 0.04}
    )

    cached.value(pos, m2018)
    cached.value(pos, m2024)

    assert inner.calls == 2
    assert cached.stats.misses == 2
    assert cached.stats.hits == 0


def test_equity_trade_key_excludes_legacy_spot_but_keeps_economics():
    position = _equity()

    # Soft model_copy of removed mark fields must not change economics hash.
    assert trade_cache_key(position) == trade_cache_key(
        position.model_copy(update={"price": 125.0})
    )
    assert trade_cache_key(position) != trade_cache_key(
        position.model_copy(update={"quantity": 20.0})
    )


def _equity_future() -> EquityFuturePosition:
    return EquityFuturePosition(
        type="equity_future",
        id="eqf1",
        symbol="ES",
        quantity=2.0,
        multiplier=50.0,
        maturity_years=0.25,
    )


def _equity_option() -> EuropeanOptionPosition:
    return EuropeanOptionPosition(
        type="european_option",
        id="eqo1",
        symbol="AAPL",
        quantity=5.0,
        strike=175.0,
        maturity_years=0.5,
        option_type="call",
    )


def _bond() -> BondPosition:
    return BondPosition(
        type="bond",
        id="bnd1",
        issuer="UST",
        face_value=1000.0,
        quantity=1.0,
        maturity_years=5.0,
        duration=4.5,
        currency="USD",
    )


def _swap() -> SwapPosition:
    return SwapPosition(
        type="swap",
        id="swp1",
        currency="USD",
        notional=1_000_000.0,
        maturity_years=5.0,
        fixed_rate=0.04,
        pay_fixed=True,
        duration=4.0,
    )


def _fx_forward() -> FXForwardPosition:
    return FXForwardPosition(
        type="fx_forward",
        id="fxf1",
        pair="EURUSD",
        notional_base=1_000_000.0,
        strike=1.08,
        maturity_years=0.5,
    )


def _fx_option() -> FXOptionPosition:
    return FXOptionPosition(
        type="fx_option",
        id="fxo1",
        pair="EURUSD",
        notional_base=1_000_000.0,
        strike=1.10,
        maturity_years=0.5,
        option_type="call",
    )


def _ir_future() -> InterestRateFuturePosition:
    return InterestRateFuturePosition(
        type="ir_future",
        id="irf1",
        currency="USD",
        quantity=10.0,
        pv01=25.0,
        maturity_years=0.25,
    )


def _cap_floor() -> CapFloorPosition:
    return CapFloorPosition(
        type="cap_floor",
        id="cap1",
        currency="USD",
        notional=1_000_000.0,
        quantity=1.0,
        strike=0.03,
        maturity_years=2.0,
        option_type="cap",
        payment_frequency_per_year=2,
    )


def _swaption() -> SwaptionPosition:
    return SwaptionPosition(
        type="swaption",
        id="swn1",
        currency="USD",
        notional=1_000_000.0,
        quantity=1.0,
        strike=0.03,
        option_maturity_years=1.0,
        swap_tenor_years=5.0,
        option_type="payer",
        payment_frequency_per_year=2,
    )


@pytest.mark.parametrize(
    ("factory", "mark_update", "econ_update"),
    [
        (_equity_future, {"spot": 4800.0, "risk_free_rate": 0.05, "dividend_yield": 0.02}, {"maturity_years": 0.5}),
        (_equity_option, {"spot": 200.0, "volatility": 0.40, "risk_free_rate": 0.05}, {"strike": 190.0}),
        (_bond, {"yield_rate": 0.06, "duration": 3.0}, {"face_value": 2000.0}),
        (_swap, {"market_swap_rate": 0.06, "duration": 3.0}, {"notional": 2_000_000.0}),
        (_fx_forward, {"spot": 1.25, "domestic_rate": 0.05, "foreign_rate": 0.01}, {"strike": 1.20}),
        (_fx_option, {"spot": 1.25, "volatility": 0.30}, {"strike": 1.20}),
        (_ir_future, {"quoted_rate": 0.05, "forward_rate": 0.055}, {"quantity": 20.0}),
        (_cap_floor, {"volatility": 0.35, "forward_rate": 0.04, "discount_rate": 0.05}, {"strike": 0.04}),
        (_swaption, {"volatility": 0.35, "forward_swap_rate": 0.04, "discount_rate": 0.05}, {"strike": 0.04}),
    ],
    ids=["equity_future", "european_option", "bond", "swap", "fx_forward", "fx_option", "ir_future", "cap_floor", "swaption"],
)
def test_trade_key_excludes_snapshot_marks_but_keeps_economics(factory, mark_update, econ_update):
    position = factory()
    assert trade_cache_key(position) == trade_cache_key(position.model_copy(update=mark_update))
    assert trade_cache_key(position) != trade_cache_key(position.model_copy(update=econ_update))


def test_bond_and_swap_trade_keys_ignore_yield_and_par_marks():
    bond = _bond()
    swap = _swap()
    assert trade_cache_key(bond) == trade_cache_key(bond.model_copy(update={"yield_rate": 0.09}))
    assert trade_cache_key(bond) != trade_cache_key(bond.model_copy(update={"quantity": 3.0}))
    assert trade_cache_key(swap) == trade_cache_key(swap.model_copy(update={"market_swap_rate": 0.09}))
    assert trade_cache_key(swap) != trade_cache_key(swap.model_copy(update={"fixed_rate": 0.05}))


@pytest.mark.parametrize(
    ("factory", "expected"),
    [
        (_equity, "e9a1a29cef3926e73f08d94692aa619e6da80ae7893af0e1eb0e691d586f1177"),
        (_equity_future, "47fd3e9b6039a6fe14622e79ff85fe141644a0fee1dd58761621dea7599c8d3a"),
        (_equity_option, "c162c5000dc5867308111f2fd7d002a490b8d728024a5d6afdf0b6b2476bb153"),
        (_bond, "7f986bfbbcb48d624ec1be8200ca85fee373baaeb28e3be163118042b3c6a825"),
        (_swap, "508caa7c5d1086b95681d6b423344183276a38857b1be55f8fb5adcc5c8400d0"),
        (_fx_forward, "7791385343a37710dc5767ed4c96220a29fc7bd65310ed80a7c63d45fc49a680"),
        (_fx_option, "28f1bbf2acf91dc2f63e931645a5ccefbe9b76c6d455b7ae963cbb7613e8da34"),
        (_ir_future, "b542ed644164dbe3ed65a5979afc012eb8f35e712ae456bc6db6f04c859f52c7"),
        (_cap_floor, "985a67f00dcc70b3c27cf91c0ad7b5e4f11c6a5c996458d42446721bd5f7fcb8"),
        (_swaption, "32b2196454ffd45aaacf20a1d6000026ee346adfea237ab734949609f22f2d4e"),
    ],
    ids=[
        "equity",
        "equity_future",
        "european_option",
        "bond",
        "swap",
        "fx_forward",
        "fx_option",
        "ir_future",
        "cap_floor",
        "swaption",
    ],
)
def test_trade_cache_key_preserves_deny_list_economics_identity(factory, expected):
    """Hashed payload must match the pre-terms deny-list economics identity."""
    assert trade_cache_key(factory()) == expected


def test_unknown_position_family_is_fail_closed():
    class _UnknownPosition:
        def model_dump(self, mode="json"):
            return {"id": "x", "yield_rate": 0.04}

    with pytest.raises(TypeError, match="terms_from_position has no terms projection"):
        trade_cache_key(_UnknownPosition())  # type: ignore[arg-type]


def test_cache_hit_skips_inner_engine():
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    pos, market = _equity(), _market()

    v1 = cached.value(pos, market)
    v2 = cached.value(pos, market)

    assert inner.calls == 1
    assert cached.stats.hits == 1
    assert cached.stats.misses == 1
    assert v1.model_dump() == v2.model_dump()
    assert v1.market_value == pytest.approx(1000.0)


def test_cache_miss_on_trade_change():
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    market = _market()
    a = _equity()
    b = a.model_copy(update={"quantity": 20})

    cached.value(a, market)
    cached.value(b, market)

    assert inner.calls == 2
    assert cached.stats.misses == 2
    assert cached.stats.hits == 0


def test_cache_invalidates_on_market_bump():
    """Market bump changes content_hash → miss; returned value reflects new spot."""
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    pos = _equity()
    base = _market(100.0)
    bumped = base.bump(EquitySpot("SPY"), 0.10)  # +10% → 110

    v_base = cached.value(pos, base)
    v_bump = cached.value(pos, bumped)
    v_base_again = cached.value(pos, base)

    assert inner.calls == 2  # base + bump; second base is a hit
    assert cached.stats.hits == 1
    assert cached.stats.misses == 2
    assert v_base.market_value == pytest.approx(1000.0)
    assert v_bump.market_value == pytest.approx(1100.0)
    assert v_base_again.market_value == pytest.approx(1000.0)
    assert market_cache_key(base) != market_cache_key(bumped)


def test_cache_miss_on_pricing_configuration_change():
    inner = CountingPricingEngine()
    cfg_a = PricingConfiguration(engine_id="CountingPricingEngine", evaluation_date="2026-09-01")
    cfg_b = PricingConfiguration(engine_id="CountingPricingEngine", evaluation_date="2026-09-02")
    a = CachedPricingEngine(inner, config=cfg_a)
    # Share the same inner counter; wrap with second config via fresh wrapper.
    b = CachedPricingEngine(inner, config=cfg_b)
    pos, market = _equity(), _market()

    a.value(pos, market)
    b.value(pos, market)

    assert inner.calls == 2
    key_a = valuation_cache_key(pos, market, cfg_a)
    key_b = valuation_cache_key(pos, market, cfg_b)
    assert key_a != key_b


def test_clear_forces_miss():
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    pos, market = _equity(), _market()

    cached.value(pos, market)
    cached.clear()
    cached.value(pos, market)

    assert inner.calls == 2
    assert cached.stats.misses == 2


def test_returned_valuation_is_copy():
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    pos, market = _equity(), _market()
    v1 = cached.value(pos, market)
    v1.market_value = -1.0  # pydantic model may allow mutation unless frozen
    v2 = cached.value(pos, market)
    assert v2.market_value == pytest.approx(1000.0)


def test_cache_requires_market():
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    pos = _equity()
    market = MarketSnapshot(id="explicit", equity_spots={"SPY": 100.0}, rates={"USD": 0.04})

    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        cached.value(pos, None)

    v1 = cached.value(pos, market)
    v2 = cached.value(pos, market)

    assert inner.calls == 1
    assert cached.stats.hits == 1
    assert v1.market_value == pytest.approx(v2.market_value)


def test_lru_eviction():
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner, maxsize=2)
    market = MarketSnapshot(
        id="m1",
        as_of="t0",
        equity_spots={"SPY": 100.0, "QQQ": 100.0, "IWM": 100.0},
        rates={"USD": 0.04},
    )
    p1 = _equity()
    p2 = p1.model_copy(update={"id": "eq2", "symbol": "QQQ"})
    p3 = p1.model_copy(update={"id": "eq3", "symbol": "IWM"})

    cached.value(p1, market)
    cached.value(p2, market)
    cached.value(p3, market)  # evicts p1
    cached.value(p1, market)  # miss again

    assert inner.calls == 4
    assert cached.stats.size == 2


def test_factory_wraps_when_cache_enabled(monkeypatch):
    monkeypatch.setenv("RISKFORGE_PRICING_ENGINE", "builtin")
    monkeypatch.setenv("RISKFORGE_PRICING_CACHE", "1")
    from app.pricing.factory import create_pricing_engine

    engine = create_pricing_engine()
    assert isinstance(engine, CachedPricingEngine)
    assert isinstance(engine.inner, BuiltinPricingEngine)


def test_factory_can_disable_cache(monkeypatch):
    monkeypatch.setenv("RISKFORGE_PRICING_ENGINE", "builtin")
    monkeypatch.setenv("RISKFORGE_PRICING_CACHE", "0")
    from app.pricing.factory import create_pricing_engine

    engine = create_pricing_engine()
    assert isinstance(engine, BuiltinPricingEngine)


def test_config_from_engine_reads_evaluation_date():
    class FakeQL(PricingEngine):
        def __init__(self) -> None:
            self.evaluation_date = date(2026, 9, 1)

        def value(self, position, market=None) -> Valuation:
            return Valuation(position_id=position.id, market_value=0.0)

    cfg = PricingConfiguration.from_engine(FakeQL())
    assert cfg.engine_id == "FakeQL"
    assert cfg.evaluation_date == "2026-09-01"
