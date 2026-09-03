from __future__ import annotations

import pytest

from app.domain.models import BondPosition, Portfolio, SwapPosition
from app.market.demo_snapshot import (
    ConflictingSampleMarkError,
    DemoSampleMarksSnapshotAdapter,
)
from app.market.snapshot import PositionMarketDataProvider
from app.pricing.builtin import BuiltinPricingEngine
from app.sample import RATES_MACRO_PORTFOLIO, demo_market_snapshot


def _usd_rate_book(*, reverse: bool = False, shared_rate: float | None = None) -> Portfolio:
    bond_rate = 0.041
    swap_rate = shared_rate if shared_rate is not None else 0.043
    positions = [
        BondPosition(
            type="bond",
            id="bond-usd",
            issuer="UST",
            face_value=1_000_000,
            maturity_years=2.0,
            yield_rate=bond_rate,
            duration=1.9,
        ),
        SwapPosition(
            type="swap",
            id="swap-usd",
            notional=1_000_000,
            maturity_years=2.0,
            fixed_rate=0.04,
            market_swap_rate=swap_rate,
            duration=1.9,
        ),
    ]
    if reverse:
        positions.reverse()
    return Portfolio(id="rates", name="rates", positions=positions)


@pytest.mark.parametrize("reverse", [False, True])
def test_unequal_duplicate_usd_marks_raise_in_both_orders(reverse: bool) -> None:
    with pytest.raises(ConflictingSampleMarkError) as exc_info:
        DemoSampleMarksSnapshotAdapter().snapshot(_usd_rate_book(reverse=reverse))

    message = str(exc_info.value)
    assert "USD" in message
    assert "bond-usd" in message
    assert "0.041" in message
    assert "swap-usd" in message
    assert "0.043" in message


def test_equal_duplicate_usd_marks_seed_one_rate() -> None:
    snapshot = DemoSampleMarksSnapshotAdapter().snapshot(
        _usd_rate_book(shared_rate=0.041)
    )

    assert dict(snapshot.rates) == {"USD": 0.041}


def test_deprecated_position_provider_inherits_conflict_behavior() -> None:
    with pytest.raises(ConflictingSampleMarkError):
        PositionMarketDataProvider().snapshot(_usd_rate_book())


def test_mixed_usd_demo_uses_explicit_snapshot_successfully() -> None:
    snapshot = demo_market_snapshot(RATES_MACRO_PORTFOLIO)

    assert snapshot.id == "demo:rates-macro"
    assert snapshot.key_rates["USD"]
    assert snapshot.projection_rates["USD"] == pytest.approx(0.0425)
    valuations = BuiltinPricingEngine().value_portfolio(
        RATES_MACRO_PORTFOLIO, snapshot
    )
    assert len(valuations) == len(RATES_MACRO_PORTFOLIO.positions)

    with pytest.raises(ConflictingSampleMarkError):
        DemoSampleMarksSnapshotAdapter().snapshot(RATES_MACRO_PORTFOLIO)
