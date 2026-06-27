"""Reported DV01 must match same-curve 1bp PARALLEL bump-and-revalue (Finding 9).

Canonical definition
--------------------
``reported DV01 = PV(snapshot.bump(RateZero(ccy, "PARALLEL"), 0.0001)) - PV(base)``
using the same curve structure as PV (snapshot curves / key rates when attached,
else the scalar ``rates[ccy]`` flat yield).

Tolerances
----------
Bonds: ``rel=1e-8``, ``abs=1e-4``. Two valuations of the same adapter on a 1bp
parallel of the *same* curve should agree to near machine precision; ``abs=1e-4``
is a tenth of a cent on a $1mm face and covers Actual365Fixed calendar-day
rounding in QuantLib ``ZeroCouponBond``. ``rel=1e-8`` catches proportional drift
on larger notionals.

Swaps / cap-floors / swaptions: same ``rel=1e-8``; ``abs=1e-4`` for swaps and
``abs=1e-6`` for option premia (smaller cash PV). Builtin bond duration DV01
(``-duration * PV * 1bp``) is *not* this definition when ``duration != maturity``.
"""
from __future__ import annotations

import pytest

from app.domain.models import (
    BondPosition,
    CapFloorPosition,
    MarketSnapshot,
    SwapPosition,
    SwaptionPosition,
)
from app.market.curves import attach_standard_usd_curves
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.factor_types import RateZero

_BP = 0.0001
_BOND_REL = 1e-8
_BOND_ABS = 1e-4
_SWAP_REL = 1e-8
_SWAP_ABS = 1e-4
_OPTION_REL = 1e-8
_OPTION_ABS = 1e-6


def _usd_curve_market(*, ir_vol: float | None = None) -> MarketSnapshot:
    """Curve-bearing USD snapshot with a *sloped* discount curve.

    ``attach_standard_usd_curves`` is the shared fixture, then selected pillars
    are shocked so ZeroCurve ≇ FlatForward(z(T)). Finding 9 is invisible on a
    flat curve: QL PV already uses the snapshot curve, but DV01 still revalues
    on ``_flat_curve(yield+1bp)``, which matches a parallel of a flat curve.
    """
    snap = MarketSnapshot(
        id="dv01-curves",
        rates={"USD": 0.04},
        ir_vols={"USD": ir_vol} if ir_vol is not None else {},
    )
    market = attach_standard_usd_curves(snap, ois_rate=0.04, sofr_rate=0.041)
    # Upward-sloping discount: short tenors down, long tenors up (KEY_TENORS).
    market = market.bump(RateZero("USD", "1Y"), -0.010)
    market = market.bump(RateZero("USD", "2Y"), -0.005)
    market = market.bump(RateZero("USD", "10Y"), 0.005)
    market = market.bump(RateZero("USD", "30Y"), 0.010)
    return market


def _bond() -> BondPosition:
    # duration ≠ maturity so duration×PV DV01 cannot sneak through.
    return BondPosition(
        type="bond",
        id="b10",
        issuer="UST",
        face_value=1_000_000.0,
        quantity=1.0,
        maturity_years=10.0,
        duration=8.0,
    )


def _swap() -> SwapPosition:
    return SwapPosition(
        type="swap",
        id="s5",
        notional=5_000_000.0,
        maturity_years=5.0,
        fixed_rate=0.04,
        pay_fixed=True,
        duration=4.3,
    )


def _cap() -> CapFloorPosition:
    return CapFloorPosition(
        type="cap_floor",
        id="usd-cap",
        currency="USD",
        notional=1_000_000.0,
        strike=0.04,
        maturity_years=2.0,
        option_type="cap",
        payment_frequency_per_year=2,
    )


def _swaption() -> SwaptionPosition:
    return SwaptionPosition(
        type="swaption",
        id="usd-payer-swaption",
        currency="USD",
        notional=1_000_000.0,
        strike=0.04,
        option_maturity_years=1.0,
        swap_tenor_years=5.0,
        option_type="payer",
        payment_frequency_per_year=2,
    )


def _assert_parallel_dv01(engine, position, market, *, rel: float, abs_: float) -> None:
    base = engine.value(position, market)
    bumped_pv = engine.value(
        position, market.bump(RateZero("USD", "PARALLEL"), _BP)
    ).market_value
    expected = bumped_pv - base.market_value
    assert base.dv01 == pytest.approx(expected, rel=rel, abs=abs_)


@pytest.fixture
def builtin_engine():
    return BuiltinPricingEngine()


@pytest.fixture
def ql_engine():
    from tests.quantlib_gate import import_quantlib

    import_quantlib()
    from app.pricing.quantlib import QuantLibPricingEngine

    return QuantLibPricingEngine()


@pytest.mark.parametrize("engine_fixture", ["builtin_engine", "ql_engine"])
def test_bond_reported_dv01_matches_curve_parallel_bump(request, engine_fixture):
    engine = request.getfixturevalue(engine_fixture)
    _assert_parallel_dv01(engine, _bond(), _usd_curve_market(), rel=_BOND_REL, abs_=_BOND_ABS)


@pytest.mark.parametrize("engine_fixture", ["builtin_engine", "ql_engine"])
def test_swap_reported_dv01_matches_curve_parallel_bump(request, engine_fixture):
    engine = request.getfixturevalue(engine_fixture)
    _assert_parallel_dv01(engine, _swap(), _usd_curve_market(), rel=_SWAP_REL, abs_=_SWAP_ABS)


@pytest.mark.parametrize("engine_fixture", ["builtin_engine", "ql_engine"])
def test_cap_floor_reported_dv01_matches_curve_parallel_bump(request, engine_fixture):
    engine = request.getfixturevalue(engine_fixture)
    market = _usd_curve_market(ir_vol=0.20)
    _assert_parallel_dv01(engine, _cap(), market, rel=_OPTION_REL, abs_=_OPTION_ABS)


@pytest.mark.parametrize("engine_fixture", ["builtin_engine", "ql_engine"])
def test_swaption_reported_dv01_matches_curve_parallel_bump(request, engine_fixture):
    engine = request.getfixturevalue(engine_fixture)
    market = _usd_curve_market(ir_vol=0.20)
    _assert_parallel_dv01(engine, _swaption(), market, rel=_OPTION_REL, abs_=_OPTION_ABS)
