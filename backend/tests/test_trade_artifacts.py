"""R0.7.2 trade-grain calculation artifact (RF-008 leftover; type + unit tests).

Conventions:
- Additive: PV and hierarchy-additive Greeks (delta, gamma, vega, dv01, fx_delta)
  parent == sum(children) within abs 1e-12 (exact binary sums in these fixtures).
- stress_pnl merges by scenario id (overlapping keys add).
- historical_pnl is omitted as None; an empty sequence is rejected (not stored).
- Sign: same as Valuation / HierarchyNode (currency PV and Greeks; stress P&L
  in currency units).
"""

from __future__ import annotations

import math

import pytest

from app.domain.models import Valuation
from app.risk.trade_artifacts import TradeCalculationArtifact

_ADDITIVE = ("pv", "delta", "gamma", "vega", "dv01", "fx_delta")


def _artifact(
    trade_id: str = "eq-a",
    *,
    pv: float = 100.0,
    delta: float = 10.0,
    gamma: float = 0.5,
    vega: float = 2.0,
    dv01: float = 0.1,
    fx_delta: float = 3.0,
    stress_pnl: dict[str, float] | None = None,
    historical_pnl: list[float] | tuple[float, ...] | None = None,
) -> TradeCalculationArtifact:
    return TradeCalculationArtifact.from_parts(
        trade_id,
        pv=pv,
        delta=delta,
        gamma=gamma,
        vega=vega,
        dv01=dv01,
        fx_delta=fx_delta,
        stress_pnl=stress_pnl,
        historical_pnl=historical_pnl,
    )


def test_from_parts_stores_pv_additive_greeks_and_optional_vectors():
    art = _artifact(
        "t-1",
        pv=50.0,
        stress_pnl={"eq_crash": -12.0},
        historical_pnl=(1.0, -2.0, 0.5),
    )
    assert art.trade_id == "t-1"
    assert art.pv == 50.0
    assert art.delta == 10.0
    assert art.gamma == 0.5
    assert art.vega == 2.0
    assert art.dv01 == 0.1
    assert art.fx_delta == 3.0
    assert dict(art.stress_pnl) == {"eq_crash": -12.0}
    assert art.historical_pnl == (1.0, -2.0, 0.5)


def test_from_valuation_maps_position_id_and_market_value():
    val = Valuation(
        position_id="bond-1",
        market_value=250.0,
        delta=1.0,
        gamma=0.0,
        vega=0.0,
        dv01=-0.04,
        fx_delta=0.0,
    )
    art = TradeCalculationArtifact.from_valuation(
        val,
        stress_pnl={"rate_up": -4.0},
        historical_pnl=[-1.0, 0.25],
    )
    assert art.trade_id == "bond-1"
    assert art.pv == 250.0
    assert art.delta == 1.0
    assert art.dv01 == -0.04
    assert dict(art.stress_pnl) == {"rate_up": -4.0}
    assert art.historical_pnl == (-1.0, 0.25)


def test_empty_trade_id_rejected():
    with pytest.raises(ValueError, match="trade_id"):
        _artifact("")
    with pytest.raises(ValueError, match="trade_id"):
        _artifact("   ")


def test_non_finite_numbers_rejected():
    with pytest.raises(ValueError, match="finite"):
        _artifact(pv=float("nan"))
    with pytest.raises(ValueError, match="finite"):
        _artifact(delta=float("inf"))
    with pytest.raises(ValueError, match="finite"):
        _artifact(stress_pnl={"eq_crash": float("nan")})
    with pytest.raises(ValueError, match="finite"):
        _artifact(historical_pnl=(1.0, float("inf")))


def test_empty_stress_key_rejected():
    with pytest.raises(ValueError, match="scenario"):
        _artifact(stress_pnl={"": -1.0})
    with pytest.raises(ValueError, match="scenario"):
        _artifact(stress_pnl={"  ": -1.0})


def test_historical_pnl_omitted_is_none_empty_sequence_rejected():
    assert _artifact().historical_pnl is None
    with pytest.raises(ValueError, match="historical"):
        _artifact(historical_pnl=())
    with pytest.raises(ValueError, match="historical"):
        _artifact(historical_pnl=[])


def test_historical_pnl_must_be_a_real_sequence():
    with pytest.raises(ValueError, match="historical"):
        _artifact(historical_pnl=1.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="historical"):
        _artifact(historical_pnl="1.0")  # type: ignore[arg-type]


def test_two_artifacts_sum_additively_on_pv_and_greeks():
    a = _artifact(
        "eq-a",
        pv=100.0,
        delta=10.0,
        gamma=0.5,
        vega=2.0,
        dv01=0.1,
        fx_delta=3.0,
    )
    b = _artifact(
        "eq-b",
        pv=40.0,
        delta=-4.0,
        gamma=0.25,
        vega=1.5,
        dv01=-0.02,
        fx_delta=1.0,
    )
    total = a + b
    assert total.pv == 140.0
    assert total.delta == 6.0
    assert total.gamma == 0.75
    assert total.vega == 3.5
    assert math.isclose(total.dv01, 0.08, abs_tol=1e-12)
    assert total.fx_delta == 4.0
    for name in _ADDITIVE:
        assert getattr(total, name) == getattr(a, name) + getattr(b, name)


def test_stress_pnl_dicts_merge_by_scenario_id():
    a = _artifact("t1", stress_pnl={"eq_crash": -10.0, "rate_up": -2.0})
    b = _artifact("t2", stress_pnl={"eq_crash": -5.0, "fx_shock": 1.5})
    merged = a + b
    assert dict(merged.stress_pnl) == {
        "eq_crash": -15.0,
        "rate_up": -2.0,
        "fx_shock": 1.5,
    }


def test_historical_vectors_add_elementwise_when_same_length():
    a = _artifact("t1", historical_pnl=(1.0, -2.0, 0.5))
    b = _artifact("t2", historical_pnl=(3.0, 1.0, -0.25))
    total = a + b
    assert total.historical_pnl == (4.0, -1.0, 0.25)


def test_historical_vector_length_mismatch_fails_closed():
    a = _artifact("t1", historical_pnl=(1.0, -2.0, 0.5))
    b = _artifact("t2", historical_pnl=(3.0, 1.0))
    with pytest.raises(ValueError, match="length"):
        _ = a + b


def test_historical_present_vs_omitted_fails_closed():
    a = _artifact("t1", historical_pnl=(1.0, -2.0))
    b = _artifact("t2", historical_pnl=None)
    with pytest.raises(ValueError, match="historical"):
        _ = a + b
