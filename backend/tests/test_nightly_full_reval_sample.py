"""R0.12.4 nightly — larger FULL_REVALUATION sample than the R0.1.4 goldens.

Skipped unless ``RISKFORGE_NIGHTLY=1`` so PR-FAST / backend-pytest stay fast.
Uses the same shocked-PV − base-PV identity as ``test_full_reval_golden.py``.
Does not change pricing engines.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from app.domain.models import EquityPosition, MarketSnapshot, Portfolio
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import full_revaluation_pnl_series
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.risk.scenarios import historical_shocked_snapshots

N_OBS = 120

pytestmark = pytest.mark.skipif(
    os.environ.get("RISKFORGE_NIGHTLY") != "1",
    reason="nightly-only larger FULL_REVALUATION sample (set RISKFORGE_NIGHTLY=1)",
)


def test_larger_full_reval_sample_matches_shocked_minus_base_pv():
    pos = EquityPosition(type="equity", id="eq", symbol="UNIT", quantity=10.0, price=100.0)
    book = Portfolio(id="nightly-full-reval", name="nightly", positions=[pos])
    market = MarketSnapshot(id="base", equity_spots={"UNIT": 100.0}, rates={"USD": 0.04})
    equity_returns = np.linspace(-0.05, 0.05, N_OBS)
    zeros = np.zeros(N_OBS)
    dataset = ArrayHistoricalDataset(
        FactorObservationSeries(
            equity_returns=equity_returns,
            vol_moves=zeros,
            rate_moves_bps=zeros,
            fx_returns=zeros,
        )
    )
    pricing = BuiltinPricingEngine()
    pnl = full_revaluation_pnl_series(book, pricing, market, dataset)
    assert pnl.shape == (N_OBS,)

    base_pv = pricing.value(book.positions[0], market).market_value
    shocked = historical_shocked_snapshots(market, dataset)
    expected = np.array(
        [pricing.value(book.positions[0], snap).market_value - base_pv for snap in shocked],
        dtype=float,
    )
    np.testing.assert_allclose(pnl, expected, atol=1e-12)
    np.testing.assert_allclose(pnl, 10.0 * 100.0 * equity_returns, atol=1e-12)
