"""Correctness tests for CachedPricingEngine (M5.5).

Units: currency market_value matching BuiltinPricingEngine.
Invariant: cache hit returns equal Valuation; market bump / trade / config change → miss.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.domain.models import EquityPosition, MarketSnapshot, Valuation
from app.interfaces.pricing import LegacyDemoPricingAdapter, PricingEngine
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
    return EquityPosition(type="equity", id="eq1", symbol="SPY", quantity=10, price=100.0)


def _market(spot: float = 100.0) -> MarketSnapshot:
    return MarketSnapshot(id="m1", as_of="t0", equity_spots={"SPY": spot}, rates={"USD": 0.04})


def test_trade_and_market_keys_stable():
    p = _equity()
    m = _market()
    assert trade_cache_key(p) == trade_cache_key(p.model_copy())
    assert market_cache_key(m) == market_cache_key(
        MarketSnapshot(id="other", as_of="later", equity_spots={"SPY": 100.0}, rates={"USD": 0.04})
    )
    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        market_cache_key(None)


def test_equity_trade_key_excludes_legacy_spot_but_keeps_economics():
    position = _equity()

    assert trade_cache_key(position) == trade_cache_key(
        position.model_copy(update={"price": 125.0})
    )
    assert trade_cache_key(position) != trade_cache_key(
        position.model_copy(update={"quantity": 20.0})
    )


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


def test_cache_requires_market_and_named_legacy_adapter_normalizes_one():
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    pos = _equity()

    with pytest.raises(ValueError, match="explicit MarketSnapshot"):
        cached.value(pos, None)

    legacy = LegacyDemoPricingAdapter(cached)
    legacy.value(pos)
    cached.value(
        pos,
        MarketSnapshot(id="explicit", equity_spots={"SPY": 100.0}, rates={}),
    )

    assert inner.calls == 1
    assert cached.stats.hits == 1


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
