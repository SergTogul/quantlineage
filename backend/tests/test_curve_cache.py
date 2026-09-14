"""Correctness tests for YieldCurve construction cache (M5.5).

Invariant: cached ``select_yield_curve`` matches uncached; rate bump → miss;
equity bump (same rates) → hit; ``QUANTLINEAGE_CURVE_CACHE=0`` disables memo.
"""

from __future__ import annotations

import pytest

from app.domain.models import MarketSnapshot
from app.market.curves import attach_standard_usd_curves
from app.pricing.curve_cache import (
    curve_cache_key,
    curve_market_fingerprint,
    get_curve_construction_cache,
    reset_curve_construction_cache,
)
from app.pricing.curve_rates import (
    _select_yield_curve_uncached,
    continuous_zero,
    select_yield_curve,
)
from app.risk.factor_types import EquitySpot, RateZero


@pytest.fixture(autouse=True)
def _fresh_curve_cache(monkeypatch):
    monkeypatch.setenv("QUANTLINEAGE_CURVE_CACHE", "1")
    monkeypatch.setenv("QUANTLINEAGE_CURVE_CACHE_SIZE", "64")
    reset_curve_construction_cache()
    yield
    reset_curve_construction_cache()


def _usd_market() -> MarketSnapshot:
    base = MarketSnapshot(
        id="m1",
        as_of="t0",
        equity_spots={"SPY": 100.0},
        rates={"USD": 0.04},
    )
    return attach_standard_usd_curves(base, ois_rate=0.04, sofr_rate=0.041)


def test_curve_cache_hit_same_market():
    market = _usd_market()
    cache = get_curve_construction_cache()

    a = select_yield_curve(market, "USD")
    b = select_yield_curve(market, "USD")

    assert a is not None and b is not None
    assert a is b  # same cached instance
    assert cache.stats.hits == 1
    assert cache.stats.misses == 1
    assert a.nodes == b.nodes


def test_curve_cache_matches_uncached_zeros():
    market = _usd_market()
    cached = select_yield_curve(market, "USD")
    plain = _select_yield_curve_uncached(market, "USD")
    assert cached is not None and plain is not None
    assert cached.nodes == plain.nodes
    assert continuous_zero(market, "USD", 5.0, fallback=0.0) == pytest.approx(
        plain.zero(5.0)
    )


def test_curve_cache_miss_on_rate_bump():
    market = _usd_market()
    cache = get_curve_construction_cache()
    bumped = market.bump(RateZero("USD", "ALL"), 0.0025)

    select_yield_curve(market, "USD")
    select_yield_curve(bumped, "USD")

    assert cache.stats.misses == 2
    assert cache.stats.hits == 0
    assert curve_market_fingerprint(market, "USD") != curve_market_fingerprint(
        bumped, "USD"
    )


def test_curve_cache_hit_when_equity_bumps():
    """Equity bump leaves rate marks unchanged → curve construction hits."""
    market = _usd_market()
    cache = get_curve_construction_cache()
    equity_bumped = market.bump(EquitySpot("SPY"), 0.10)

    c1 = select_yield_curve(market, "USD")
    c2 = select_yield_curve(equity_bumped, "USD")

    assert c1 is c2
    assert cache.stats.hits == 1
    assert cache.stats.misses == 1
    assert curve_cache_key(market, "USD", prefer_projection=False) == curve_cache_key(
        equity_bumped, "USD", prefer_projection=False
    )


def test_curve_cache_prefer_projection_separate_key():
    market = _usd_market()
    cache = get_curve_construction_cache()

    discount = select_yield_curve(market, "USD", prefer_projection=False)
    projection = select_yield_curve(market, "USD", prefer_projection=True)

    assert discount is not None and projection is not None
    assert discount.curve_type == "discount"
    assert projection.curve_type == "projection"
    assert cache.stats.misses == 2
    assert discount is not projection


def test_curve_cache_disabled(monkeypatch):
    monkeypatch.setenv("QUANTLINEAGE_CURVE_CACHE", "0")
    reset_curve_construction_cache()
    market = _usd_market()

    a = select_yield_curve(market, "USD")
    b = select_yield_curve(market, "USD")

    assert a is not None and b is not None
    assert a is not b  # freshly constructed each call
    assert a.nodes == b.nodes
    # Disabled path never touches the process cache.
    assert get_curve_construction_cache().stats.requests == 0
