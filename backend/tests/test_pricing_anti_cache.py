"""R0.6.4 — unique-shock FULL_REVALUATION must not pay the valuation LRU tax.

Invariant: repeated base snapshot valuations may hit; unique shocked snapshots
bypass get/put and still match the inner engine (abs 1e-12).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest

from app.domain.models import (
    EquityPosition,
    MarketSnapshot,
    Portfolio,
    StressScenario,
    Valuation,
)
from app.interfaces.pricing import PricingEngine
from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.cache import CachedPricingEngine, bypass_valuation_lru, valuation_cache_key
from app.risk.historical import full_revaluation_pnl_series
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.risk.var import VaRAnalytics


class CountingPricingEngine(PricingEngine):
    def __init__(self) -> None:
        self.calls = 0
        self._inner = BuiltinPricingEngine()

    def value(self, position, market=None) -> Valuation:
        self.calls += 1
        return self._inner.value(position, market)


def _equity() -> EquityPosition:
    return EquityPosition(type="equity", id="eq", symbol="UNIT", quantity=10.0)


def _book() -> Portfolio:
    return Portfolio(id="anti-cache", name="anti-cache", positions=[_equity()])


def _market() -> MarketSnapshot:
    return MarketSnapshot(id="base", as_of="t0", equity_spots={"UNIT": 100.0}, rates={"USD": 0.04})


def _dataset() -> ArrayHistoricalDataset:
    equity_returns = np.array([-0.1, 0.0, 0.05], dtype=float)
    zeros = np.zeros_like(equity_returns)
    return ArrayHistoricalDataset(
        FactorObservationSeries(
            equity_returns=equity_returns,
            vol_moves=zeros,
            rate_moves_bps=zeros,
            fx_returns=zeros,
        )
    )


def _spy_lru_gets(cached: CachedPricingEngine) -> list[str]:
    gets: list[str] = []
    cache = cached._cache
    orig_get = cache.get

    def spy_get(key: str, default: object = None) -> object:
        gets.append(key)
        return orig_get(key, default)

    cache.get = spy_get  # type: ignore[method-assign]
    return gets


def test_bypass_context_does_not_consult_or_populate_lru():
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    pos, market = _equity(), _market()
    gets = _spy_lru_gets(cached)

    with bypass_valuation_lru():
        v = cached.value(pos, market)

    assert inner.calls == 1
    assert gets == []
    assert cached.stats.hits == 0
    assert cached.stats.misses == 0
    assert cached.stats.size == 0
    assert v.market_value == pytest.approx(1000.0)


def test_bypass_does_not_build_per_snapshot_cache_keys(monkeypatch: pytest.MonkeyPatch):
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    calls: list[tuple[object, ...]] = []
    real_key: Callable[..., str] = valuation_cache_key

    def counting_key(*args: object, **kwargs: object) -> str:
        calls.append(args)
        return real_key(*args, **kwargs)

    monkeypatch.setattr("app.pricing.cache.valuation_cache_key", counting_key)

    with bypass_valuation_lru():
        cached.value(_equity(), _market())

    assert calls == []
    assert inner.calls == 1


def test_repeated_base_still_hits_outside_bypass():
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    pos, market = _equity(), _market()

    v1 = cached.value(pos, market)
    v2 = cached.value(pos, market)

    assert inner.calls == 1
    assert cached.stats.hits == 1
    assert cached.stats.misses == 1
    assert v1.market_value == pytest.approx(v2.market_value)


def test_unique_shock_full_reval_does_not_consult_lru(monkeypatch: pytest.MonkeyPatch):
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    book, market, dataset = _book(), _market(), _dataset()
    gets = _spy_lru_gets(cached)
    key_calls: list[tuple[object, ...]] = []
    real_key: Callable[..., str] = valuation_cache_key

    def counting_key(*args: object, **kwargs: object) -> str:
        key_calls.append(args)
        return real_key(*args, **kwargs)

    monkeypatch.setattr("app.pricing.cache.valuation_cache_key", counting_key)

    pnl = full_revaluation_pnl_series(book, cached, market, dataset)

    n_obs = dataset.factor_observations().n_observations
    assert inner.calls == 1 + n_obs
    assert cached.stats.size == 1
    assert cached.stats.misses == 1
    assert cached.stats.hits == 0
    assert len(key_calls) == 1
    assert len(set(gets)) == 1
    np.testing.assert_allclose(pnl, np.array([-100.0, 0.0, 50.0]), atol=1e-12)


def test_unique_shock_full_reval_matches_uncached_inner():
    book, market, dataset = _book(), _market(), _dataset()
    cached = CachedPricingEngine(BuiltinPricingEngine())
    cold = BuiltinPricingEngine()

    cached_pnl = full_revaluation_pnl_series(book, cached, market, dataset)
    cold_pnl = full_revaluation_pnl_series(book, cold, market, dataset)

    np.testing.assert_allclose(cached_pnl, cold_pnl, atol=1e-12)
    np.testing.assert_allclose(cached_pnl, np.array([-100.0, 0.0, 50.0]), atol=1e-12)


def test_var_analytics_unique_shock_full_reval_does_not_consult_lru(monkeypatch: pytest.MonkeyPatch):
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    book, market, dataset = _book(), _market(), _dataset()
    gets = _spy_lru_gets(cached)
    key_calls: list[tuple[object, ...]] = []
    real_key: Callable[..., str] = valuation_cache_key

    def counting_key(*args: object, **kwargs: object) -> str:
        key_calls.append(args)
        return real_key(*args, **kwargs)

    monkeypatch.setattr("app.pricing.cache.valuation_cache_key", counting_key)

    pnl = VaRAnalytics(dataset=dataset)._full_reval_position_pnls(book, cached, market)

    n_obs = dataset.factor_observations().n_observations
    assert inner.calls == 1 + n_obs
    assert cached.stats.size == 1
    assert cached.stats.misses == 1
    assert cached.stats.hits == 0
    assert len(key_calls) == 1
    assert len(set(gets)) == 1
    np.testing.assert_allclose(pnl["eq"], np.array([-100.0, 0.0, 50.0]), atol=1e-12)


def test_base_lru_hit_survives_unique_shock_bypass():
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    book, market, dataset = _book(), _market(), _dataset()

    full_revaluation_pnl_series(book, cached, market, dataset)
    after_reval = inner.calls
    again = cached.value(book.positions[0], market)

    assert inner.calls == after_reval
    assert cached.stats.hits == 1
    assert again.market_value == pytest.approx(1000.0)


def test_shocked_value_bypasses_per_snapshot_lru():
    inner = CountingPricingEngine()
    cached = CachedPricingEngine(inner)
    gets = _spy_lru_gets(cached)
    scenario = StressScenario(id="crash", name="crash", equity_shock=-0.10)

    pv = cached.shocked_value(_equity(), scenario, _market())

    assert inner.calls == 1
    assert gets == []
    assert cached.stats.size == 0
    assert pv == pytest.approx(900.0)
