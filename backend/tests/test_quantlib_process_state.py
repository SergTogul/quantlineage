"""R0.1.5 — QuantLib process-global state regression.

Documents current ownership (RF-002) before R0.3 introduces a process-owned
session. These tests must keep passing while they pin today's behavior, and
they must fail if someone later claims instance RLock isolation equals
process isolation.

Pinned facts:
- ``QuantLibPricingEngine._lock`` is per instance.
- ``ql.Settings.evaluationDate`` is process-global.
- Engine ``evaluation_date`` (not ``MarketSnapshot.as_of``) drives the adapter.
- Default ``evaluation_date`` is ``date.today()`` (wall-clock).
- Swap valuations seed USDLibor fixings onto the process IndexManager.
"""

from __future__ import annotations

import threading
import time
from datetime import date

import pytest
from tests.quantlib_gate import import_quantlib

ql = import_quantlib()

from app.domain.models import BondPosition, MarketSnapshot, SwapPosition
from app.pricing.quantlib import QuantLibPricingEngine


def _bond() -> BondPosition:
    return BondPosition(
        type="bond",
        id="zc",
        issuer="UST",
        face_value=1_000_000,
        quantity=1,
        maturity_years=10.0,
        yield_rate=0.04,
        duration=8.0,
    )


def test_two_engine_instances_do_not_share_a_lock():
    """Instance RLock cannot serialize process-global QuantLib Settings."""
    a = QuantLibPricingEngine(evaluation_date=date(2020, 1, 2))
    b = QuantLibPricingEngine(evaluation_date=date(2024, 6, 14))
    assert a._lock is not b._lock
    assert a._lock is not QuantLibPricingEngine._lock if hasattr(QuantLibPricingEngine, "_lock") else True


def test_sequential_engines_write_their_own_evaluation_dates_into_settings():
    """Each engine sets process-global Settings.evaluationDate to its own date.

    Domain maturities are years-from-eval, so ZCB PV can be identical across
    dates; the observable that must differ is the QuantLib settings date itself.
    """
    early = QuantLibPricingEngine(evaluation_date=date(2020, 1, 2))
    late = QuantLibPricingEngine(evaluation_date=date(2024, 6, 14))
    with early._session():
        d_early = ql.Settings.instance().evaluationDate
        assert d_early == early._ql_date(date(2020, 1, 2))
    with late._session():
        d_late = ql.Settings.instance().evaluationDate
        assert d_late == late._ql_date(date(2024, 6, 14))
    assert d_early != d_late
    # After both sessions, a new nested session on ``early`` still uses 2020.
    with early._session():
        assert ql.Settings.instance().evaluationDate == early._ql_date(date(2020, 1, 2))


def test_overlapping_sessions_let_second_engine_overwrite_evaluation_date():
    """R0.1.5: overlapping instance sessions are not process-serialized.

    Pins current unsafe behavior. R0.3 must replace this with isolation.
    """
    a = QuantLibPricingEngine(evaluation_date=date(2020, 1, 2))
    b = QuantLibPricingEngine(evaluation_date=date(2024, 6, 14))
    a_inside = threading.Event()
    b_inside = threading.Event()
    a_observed: list = []
    errors: list[str] = []

    def run_a() -> None:
        try:
            with a._session():
                a_inside.set()
                if not b_inside.wait(timeout=5):
                    errors.append("B did not enter; instance locks unexpectedly serialized")
                    return
                a_observed.append(ql.Settings.instance().evaluationDate)
        except Exception as exc:  # pragma: no cover - diagnostic
            errors.append(repr(exc))

    def run_b() -> None:
        try:
            if not a_inside.wait(timeout=5):
                errors.append("A did not enter session")
                return
            with b._session():
                b_inside.set()
                deadline = time.time() + 5
                while not a_observed and time.time() < deadline:
                    time.sleep(0.01)
        except Exception as exc:  # pragma: no cover - diagnostic
            errors.append(repr(exc))

    ta = threading.Thread(target=run_a)
    tb = threading.Thread(target=run_b)
    ta.start()
    tb.start()
    ta.join(timeout=10)
    tb.join(timeout=10)
    assert not errors, errors
    assert a_observed, "A never sampled Settings.evaluationDate"
    assert a_observed[0] == b._ql_date(date(2024, 6, 14))


def test_snapshot_as_of_does_not_drive_quantlib_evaluation_date():
    """Current gap: snapshot as_of is unused; engine.evaluation_date wins.

    ZCB PV is *not* a date probe here: domain maturity is years-from-eval, so
    PV can stay identical if as_of started driving Settings. This test only
    records that two snapshots with different as_of strings still price under
    the same engine.evaluation_date. R0.3 must observe Settings.evaluationDate
    from snapshot/run as_of.
    """
    engine = QuantLibPricingEngine(evaluation_date=date(2020, 1, 2))
    bond = _bond()
    market_old = MarketSnapshot(id="old", as_of="2018-01-01", rates={"USD": 0.04})
    market_new = MarketSnapshot(id="new", as_of="2024-06-14", rates={"USD": 0.04})
    assert engine.value(bond, market_old).market_value == pytest.approx(
        engine.value(bond, market_new).market_value, rel=1e-12, abs=1e-8
    )


def test_default_evaluation_date_is_wall_clock_today():
    engine = QuantLibPricingEngine()
    assert engine.evaluation_date == date.today()


def test_swap_valuation_leaves_ibor_fixings_in_process():
    """IndexManager is process-global; valuations seed fixings and do not clear them."""
    mgr = ql.IndexManager.instance()
    mgr.clearHistories()
    engine = QuantLibPricingEngine(evaluation_date=date(2024, 6, 14))
    swap = SwapPosition(
        type="swap",
        id="irs",
        notional=5_000_000,
        maturity_years=2.0,
        fixed_rate=0.03,
        market_swap_rate=0.04,
        pay_fixed=True,
        duration=1.8,
    )
    try:
        engine.value(swap)
        histories = list(mgr.histories())
        assert len(histories) >= 1
        joined = " ".join(str(h) for h in histories).lower()
        assert "libor" in joined or "usd" in joined
    finally:
        mgr.clearHistories()
