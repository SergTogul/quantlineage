"""R0.6.3 - QuantLib full-revaluation reuse keeps shocked market state live."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from tests.quantlib_gate import import_quantlib

ql = import_quantlib()

import app.pricing.quantlib as quantlib_mod
from app.domain.models import EuropeanOptionPosition, MarketSnapshot, Portfolio
from app.pricing.quantlib import QuantLibPricingEngine
from app.risk.historical import full_revaluation_pnl_series
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries
from app.risk.scenarios import iter_historical_shocked_snapshots


def _option_book() -> Portfolio:
    return Portfolio(
        id="reuse-book",
        name="Reuse Book",
        positions=[
            EuropeanOptionPosition(
                type="european_option",
                id="abc-call",
                symbol="ABC",
                quantity=25.0,
                strike=100.0,
                maturity_years=1.0,
                option_type="call",
            )
        ],
    )


def _market() -> MarketSnapshot:
    return MarketSnapshot(
        id="reuse-market",
        as_of=date(2026, 9, 1),
        equity_spots={"ABC": 100.0},
        equity_vols={"ABC": 0.20},
        rates={"USD": 0.03},
        dividend_yields={"ABC": 0.01},
    )


def _dataset() -> ArrayHistoricalDataset:
    return ArrayHistoricalDataset(
        FactorObservationSeries(
            equity_returns=np.array([-0.05, 0.0, 0.03, 0.07], dtype=float),
            vol_moves=np.array([0.10, 0.0, -0.04, 0.03], dtype=float),
            rate_moves_bps=np.array([12.0, 0.0, -8.0, 4.0], dtype=float),
            fx_returns=np.zeros(4, dtype=float),
        )
    )


def test_scalar_option_full_reval_reuses_vanilla_option_structure(monkeypatch):
    book = _option_book()
    market = _market()
    dataset = _dataset()
    engine = QuantLibPricingEngine(evaluation_date=date(2026, 9, 1))
    constructed = 0
    real_vanilla_option = quantlib_mod.ql.VanillaOption

    def counting_vanilla_option(*args, **kwargs):
        nonlocal constructed
        constructed += 1
        return real_vanilla_option(*args, **kwargs)

    monkeypatch.setattr(quantlib_mod.ql, "VanillaOption", counting_vanilla_option)

    pnl = full_revaluation_pnl_series(book, engine, market, dataset)

    assert pnl.shape == (4,)
    assert constructed == 1


def test_scalar_option_full_reval_reuse_matches_cold_valuations():
    book = _option_book()
    market = _market()
    dataset = _dataset()
    engine = QuantLibPricingEngine(evaluation_date=date(2026, 9, 1))
    base_mv = sum(
        QuantLibPricingEngine(evaluation_date=date(2026, 9, 1))
        .value(position, market)
        .market_value
        for position in book.positions
    )
    expected = np.asarray(
        [
            sum(
                QuantLibPricingEngine(evaluation_date=date(2026, 9, 1))
                .value(position, shocked)
                .market_value
                for position in book.positions
            )
            - base_mv
            for shocked in iter_historical_shocked_snapshots(market, dataset)
        ],
        dtype=float,
    )

    actual = full_revaluation_pnl_series(book, engine, market, dataset)

    assert actual == pytest.approx(expected, rel=0.0, abs=1e-12)
