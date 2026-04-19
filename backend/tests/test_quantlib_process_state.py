"""R0.3 / RF-002 — process-owned QuantLib session.

Pins the ownership boundary that R0.1.5 exposed as unsafe:

- ``QuantLibPricingEngine`` instances share one process-level lock
  (module-owned, not allocated in ``__init__``).
- Overlapping sessions serialize; restoring per-instance locks fails Acc 5.
- Parseable snapshot ``as_of`` drives ``Settings.evaluationDate``, not wall-clock.
- A valuation must not leave IndexManager fixing history for the next one.
"""

from __future__ import annotations

import threading
import time
from datetime import date

import pytest
from tests.quantlib_gate import import_quantlib
from app.interfaces.pricing import LegacyDemoPricingAdapter

ql = import_quantlib()

from app.domain.models import BondPosition, MarketSnapshot, SwapPosition
from app.pricing import quantlib as quantlib_mod
from app.pricing.cache import CachedPricingEngine
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


def _swap() -> SwapPosition:
    return SwapPosition(
        type="swap",
        id="irs",
        notional=5_000_000,
        maturity_years=2.0,
        fixed_rate=0.03,
        market_swap_rate=0.04,
        pay_fixed=True,
        duration=1.8,
    )


def test_two_engine_instances_share_process_lock():
    """Process lock is shared; per-instance RLock must not be the serialiser."""
    a = QuantLibPricingEngine(evaluation_date=date(2020, 1, 2))
    b = QuantLibPricingEngine(evaluation_date=date(2024, 6, 14))
    assert a._lock is b._lock
    assert a._lock is quantlib_mod._QL_PROCESS_LOCK
    assert a._lock is QuantLibPricingEngine._process_lock


def test_sequential_engines_write_their_own_evaluation_dates_into_settings():
    """Each session still sets process-global Settings to its own date."""
    early = QuantLibPricingEngine(evaluation_date=date(2020, 1, 2))
    late = QuantLibPricingEngine(evaluation_date=date(2024, 6, 14))
    with early._session():
        d_early = ql.Settings.instance().evaluationDate
        assert d_early == early._ql_date(date(2020, 1, 2))
    with late._session():
        d_late = ql.Settings.instance().evaluationDate
        assert d_late == late._ql_date(date(2024, 6, 14))
    assert d_early != d_late
    with early._session():
        assert ql.Settings.instance().evaluationDate == early._ql_date(date(2020, 1, 2))


def test_overlapping_sessions_are_serialized_by_process_lock():
    """Acc 5: two engines cannot interleave Settings.evaluationDate.

    If per-instance locks are restored, B enters while A holds the session
    and A observes B's evaluation date — this test must fail.
    """
    a = QuantLibPricingEngine(evaluation_date=date(2020, 1, 2))
    b = QuantLibPricingEngine(evaluation_date=date(2024, 6, 14))
    a_inside = threading.Event()
    a_observed: list = []
    b_entered_before_a_sampled = threading.Event()
    errors: list[str] = []

    def run_a() -> None:
        try:
            with a._session():
                a_inside.set()
                # Window long enough that an instance lock would let B in.
                time.sleep(0.2)
                a_observed.append(ql.Settings.instance().evaluationDate)
        except Exception as exc:  # pragma: no cover - diagnostic
            errors.append(repr(exc))

    def run_b() -> None:
        try:
            if not a_inside.wait(timeout=5):
                errors.append("A did not enter session")
                return
            with b._session():
                if not a_observed:
                    b_entered_before_a_sampled.set()
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
    assert a_observed[0] == a._ql_date(date(2020, 1, 2))
    assert not b_entered_before_a_sampled.is_set(), (
        "B entered while A held the session — process lock is not shared"
    )


def test_snapshot_as_of_drives_quantlib_evaluation_date():
    """R0.3.4: same trade, two explicit as-of dates; snapshot drives QuantLib.

    Domain ZCB maturity is years-from-eval, so PV is not the probe. Settings
    during pricing must match snapshot as_of, not the engine wall-clock default.
    """
    observed: list = []
    engine = QuantLibPricingEngine()
    wall_clock = engine._ql_date(date.today())
    original_bond = engine._bond

    def spy_bond(position, market=None):
        observed.append(ql.Settings.instance().evaluationDate)
        return original_bond(position, market)

    engine._bond = spy_bond
    bond = _bond()
    engine.value(bond, MarketSnapshot(id="old", as_of="2018-01-01", rates={"USD": 0.04}))
    engine.value(bond, MarketSnapshot(id="new", as_of="2024-06-14", rates={"USD": 0.04}))

    assert len(observed) == 2
    assert observed[0] == engine._ql_date(date(2018, 1, 1))
    assert observed[1] == engine._ql_date(date(2024, 6, 14))
    assert observed[0] != wall_clock
    assert observed[1] != wall_clock
    # Constructor fallback stays wall-clock when no parseable as_of is supplied.
    assert engine.evaluation_date == date.today()


def test_unparseable_as_of_keeps_engine_evaluation_date():
    """Labels such as ``current`` / ``t0`` must not silently change the eval date."""
    observed: list = []
    engine = QuantLibPricingEngine(evaluation_date=date(2020, 1, 2))
    original_bond = engine._bond

    def spy_bond(position, market=None):
        observed.append(ql.Settings.instance().evaluationDate)
        return original_bond(position, market)

    engine._bond = spy_bond
    engine.value(_bond(), MarketSnapshot(id="lab", as_of="t0", rates={"USD": 0.04}))
    assert observed == [engine._ql_date(date(2020, 1, 2))]


def test_typed_date_as_of_drives_quantlib_evaluation_date():
    """R0.3.1: a domain ``date`` as_of drives Settings, not wall-clock."""
    observed: list = []
    engine = QuantLibPricingEngine()
    wall_clock = engine._ql_date(date.today())
    original_bond = engine._bond

    def spy_bond(position, market=None):
        observed.append(ql.Settings.instance().evaluationDate)
        return original_bond(position, market)

    engine._bond = spy_bond
    engine.value(
        _bond(),
        MarketSnapshot(id="typed", as_of=date(2018, 1, 1), rates={"USD": 0.04}),
    )
    assert observed == [engine._ql_date(date(2018, 1, 1))]
    assert observed[0] != wall_clock


def test_default_evaluation_date_is_wall_clock_today():
    engine = QuantLibPricingEngine()
    assert engine.evaluation_date == date.today()


def test_swap_valuation_does_not_leave_ibor_fixings():
    """R0.3.3: session must not leak IndexManager histories to the next valuation."""
    mgr = ql.IndexManager.instance()
    mgr.clearHistories()
    engine = QuantLibPricingEngine(evaluation_date=date(2024, 6, 14))
    try:
        LegacyDemoPricingAdapter(engine).value(_swap())
        assert list(mgr.histories()) == []
    finally:
        mgr.clearHistories()


def test_second_swap_valuation_does_not_see_prior_fixings():
    """A later valuation starts without the previous session's USDLibor series."""
    mgr = ql.IndexManager.instance()
    mgr.clearHistories()
    early = QuantLibPricingEngine(evaluation_date=date(2020, 1, 2))
    late = QuantLibPricingEngine(evaluation_date=date(2024, 6, 14))
    try:
        LegacyDemoPricingAdapter(early).value(_swap())
        assert list(mgr.histories()) == []
        LegacyDemoPricingAdapter(late).value(_swap())
        assert list(mgr.histories()) == []
    finally:
        mgr.clearHistories()


def test_factory_cache_does_not_reuse_pv_across_iso_as_of(monkeypatch):
    """R0.3 Important #1: factory cache must miss when parseable as_of changes.

    Same 2Y USDLibor payer swap and marks; 2018 then 2024 must return the
    unwrapped 2024 PV, not the 2018 cached PV.
    """
    monkeypatch.setenv("RISKFORGE_PRICING_ENGINE", "quantlib")
    monkeypatch.setenv("RISKFORGE_PRICING_CACHE", "1")
    from app.pricing.factory import create_pricing_engine

    swap = _swap()
    marks = {"USD": 0.04}
    m2018 = MarketSnapshot(id="old", as_of="2018-01-01", rates=marks)
    m2024 = MarketSnapshot(id="new", as_of="2024-06-14", rates=marks)

    unwrapped = QuantLibPricingEngine()
    expected_2018 = unwrapped.value(swap, m2018).market_value
    expected_2024 = unwrapped.value(swap, m2024).market_value
    assert expected_2018 != pytest.approx(expected_2024)

    engine = create_pricing_engine()
    assert isinstance(engine, CachedPricingEngine)
    factory_2018 = engine.value(swap, m2018).market_value
    factory_2024 = engine.value(swap, m2024).market_value

    assert factory_2018 == pytest.approx(expected_2018)
    assert factory_2024 == pytest.approx(expected_2024)
    assert factory_2024 != pytest.approx(expected_2018)
