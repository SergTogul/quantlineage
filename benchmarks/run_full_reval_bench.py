#!/usr/bin/env python3
"""R0.6.1 / R0.6.7 / RF-007 — FULL_REVALUATION identity + acceptance benches (not a host SLA).

Reuses the nightly 120-obs unit-equity sample
(``backend/tests/test_nightly_full_reval_sample.py``): shocked PV − base PV.
Emits JSON with ``impl``, ``n_obs``, and a SHA-256 checksum of the rounded
P&L vector. Wall time is recorded for operators but is **not** an SLA: do
not treat a recorded wall time, RSS, or scenarios/sec as a floor.

R0.6.7 acceptance (PR-safe default N=10 × S=50, above 1×120) records peak
RSS, scenarios/sec, builtin vs QuantLib at the same N×S, and warm vs cold
``wall_ms`` on the same fixture. QuantLib is skip-or-run (fail-closed when
``RISKFORGE_REQUIRE_QUANTLIB=1``). Do not invoke ``benchmarks/check_m6_sla.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.models import EquityPosition, MarketSnapshot, Portfolio  # noqa: E402
from app.pricing.builtin import BuiltinPricingEngine  # noqa: E402
from app.risk.historical import full_revaluation_pnl_series  # noqa: E402
from app.risk.historical_data import ArrayHistoricalDataset, FactorObservationSeries  # noqa: E402

IMPL = "full_reval_builtin"
IMPL_QUANTLIB = "full_reval_quantlib"
N_OBS = 120
N_POSITIONS = 1
ACCEPTANCE_N_POSITIONS = 10
ACCEPTANCE_N_OBS = 50
QUANTITY = 10.0
SPOT = 100.0
# SHA-256 of rounded engine P&L lines (allclose 1e-12 to 10 * 100 * linspace(-0.05, 0.05, 120)).
EXPECTED_CHECKSUM = "6602fa6906f2579f5c89af72a41ab274c07650234fff69387bc2202b5a40534f"
# SHA-256 of rounded engine P&L for 10 UNIT equities × linspace(-0.05, 0.05, 50).
EXPECTED_ACCEPTANCE_CHECKSUM = "a28cf4ee6199bf40da3f2598f4241fc85fa4adc4f86bccbbd97e4938047d7537"

_TRUTHY = {"1", "true", "yes", "on"}


def _quantlib_required() -> bool:
    return os.environ.get("RISKFORGE_REQUIRE_QUANTLIB", "").strip().lower() in _TRUTHY


def _peak_rss_kib() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    rss = float(usage.ru_maxrss)
    if sys.platform == "darwin":
        return rss / 1024.0  # bytes → KiB
    return rss  # Linux: already KiB


def bench_book() -> tuple[Portfolio, MarketSnapshot, ArrayHistoricalDataset]:
    pos = EquityPosition(type="equity", id="eq", symbol="UNIT", quantity=QUANTITY)
    book = Portfolio(id="r061-full-reval", name="r061", positions=[pos])
    market = MarketSnapshot(id="base", equity_spots={"UNIT": SPOT}, rates={"USD": 0.04})
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
    return book, market, dataset


def acceptance_book(
    n_positions: int, n_obs: int
) -> tuple[Portfolio, MarketSnapshot, ArrayHistoricalDataset]:
    positions = [
        EquityPosition(type="equity", id=f"eq{i:02d}", symbol=f"UNIT_{i:02d}", quantity=QUANTITY)
        for i in range(n_positions)
    ]
    book = Portfolio(id="r067-full-reval", name="r067", positions=positions)
    spots = {f"UNIT_{i:02d}": SPOT for i in range(n_positions)}
    market = MarketSnapshot(id="base", equity_spots=spots, rates={"USD": 0.04})
    equity_returns = np.linspace(-0.05, 0.05, n_obs)
    zeros = np.zeros(n_obs)
    dataset = ArrayHistoricalDataset(
        FactorObservationSeries(
            equity_returns=equity_returns,
            vol_moves=zeros,
            rate_moves_bps=zeros,
            fx_returns=zeros,
        )
    )
    return book, market, dataset


def pnl_checksum(pnl: np.ndarray) -> str:
    lines = "\n".join(f"{x:.12f}" for x in pnl)
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def _scenarios_per_sec(n_obs: int, wall_ms: float) -> float:
    elapsed_s = float(wall_ms) / 1000.0
    if elapsed_s <= 0.0:
        return 0.0
    return float(n_obs) / elapsed_s


def _time_pnl_series(book, pricing, market, dataset) -> tuple[np.ndarray, float, float]:
    rss_before = _peak_rss_kib()
    started = time.perf_counter()
    pnl = full_revaluation_pnl_series(book, pricing, market, dataset)
    wall_ms = (time.perf_counter() - started) * 1000.0
    rss_after = _peak_rss_kib()
    return pnl, wall_ms, max(rss_before, rss_after)


def _engine_row(
    *,
    impl: str,
    n_positions: int,
    n_obs: int,
    pricing,
    book,
    market,
    dataset,
    expected_checksum: str | None,
) -> dict:
    pnl_cold, wall_ms_cold, rss_cold = _time_pnl_series(book, pricing, market, dataset)
    pnl_warm, wall_ms_warm, rss_warm = _time_pnl_series(book, pricing, market, dataset)
    if pnl_cold.shape != (n_obs,) or pnl_warm.shape != (n_obs,):
        raise AssertionError(f"n_obs {pnl_cold.shape} / {pnl_warm.shape} != {(n_obs,)}")
    expected = float(n_positions) * QUANTITY * SPOT * dataset.factor_observations().equity_returns
    if not np.allclose(pnl_cold, expected, atol=1e-12):
        raise AssertionError("P&L does not match shocked-PV − base-PV identity")
    if not np.allclose(pnl_warm, pnl_cold, atol=1e-12):
        raise AssertionError("warm P&L differs from cold P&L")
    checksum = pnl_checksum(pnl_cold)
    if expected_checksum is not None and checksum != expected_checksum:
        raise AssertionError(f"checksum {checksum} != {expected_checksum}")
    wall_ms = wall_ms_cold
    return {
        "impl": impl,
        "n_obs": n_obs,
        "n_positions": n_positions,
        "checksum": checksum,
        "pnl_identity_ok": True,
        "wall_ms": wall_ms,
        "wall_ms_cold": wall_ms_cold,
        "wall_ms_warm": wall_ms_warm,
        "peak_rss_kib": max(rss_cold, rss_warm),
        "scenarios_per_sec": _scenarios_per_sec(n_obs, wall_ms_cold),
        "available": True,
    }


def run_quantlib_acceptance(
    n_positions: int, n_obs: int, expected_checksum: str | None
) -> dict:
    book, market, dataset = acceptance_book(n_positions, n_obs)
    try:
        from app.pricing.quantlib import QuantLibPricingEngine, QuantLibUnavailableError
    except ImportError as exc:
        if _quantlib_required():
            raise RuntimeError(
                "QuantLib is required (RISKFORGE_REQUIRE_QUANTLIB=1) but could not "
                "be imported. Install backend/requirements.txt including QuantLib."
            ) from exc
        return {
            "impl": IMPL_QUANTLIB,
            "n_positions": n_positions,
            "n_obs": n_obs,
            "available": False,
            "skip_reason": "QuantLib is not installed",
        }
    try:
        pricing = QuantLibPricingEngine()
    except QuantLibUnavailableError as exc:
        if _quantlib_required():
            raise
        return {
            "impl": IMPL_QUANTLIB,
            "n_positions": n_positions,
            "n_obs": n_obs,
            "available": False,
            "skip_reason": str(exc) or "QuantLib is not installed",
        }
    row = _engine_row(
        impl=IMPL_QUANTLIB,
        n_positions=n_positions,
        n_obs=n_obs,
        pricing=pricing,
        book=book,
        market=market,
        dataset=dataset,
        expected_checksum=expected_checksum,
    )
    return row


def run_acceptance_matrix(n_positions: int, n_obs: int) -> dict:
    book, market, dataset = acceptance_book(n_positions, n_obs)
    pin = EXPECTED_ACCEPTANCE_CHECKSUM
    if n_positions != ACCEPTANCE_N_POSITIONS or n_obs != ACCEPTANCE_N_OBS:
        pin = None
    builtin = _engine_row(
        impl=IMPL,
        n_positions=n_positions,
        n_obs=n_obs,
        pricing=BuiltinPricingEngine(),
        book=book,
        market=market,
        dataset=dataset,
        expected_checksum=pin,
    )
    quantlib = run_quantlib_acceptance(n_positions, n_obs, expected_checksum=pin)
    return {
        "n_positions": n_positions,
        "n_obs": n_obs,
        "builtin": builtin,
        "quantlib": quantlib,
    }


def run_full_reval_identity(
    *,
    acceptance_n_positions: int = ACCEPTANCE_N_POSITIONS,
    acceptance_n_obs: int = ACCEPTANCE_N_OBS,
) -> dict:
    book, market, dataset = bench_book()
    pricing = BuiltinPricingEngine()
    started = time.perf_counter()
    pnl = full_revaluation_pnl_series(book, pricing, market, dataset)
    wall_ms = (time.perf_counter() - started) * 1000.0
    if pnl.shape != (N_OBS,):
        raise AssertionError(f"n_obs {pnl.shape[0]} != {N_OBS}")
    expected = QUANTITY * SPOT * dataset.factor_observations().equity_returns
    if not np.allclose(pnl, expected, atol=1e-12):
        raise AssertionError("P&L does not match shocked-PV − base-PV identity")
    checksum = pnl_checksum(pnl)
    if EXPECTED_CHECKSUM != "PENDING_LOCAL_PIN" and checksum != EXPECTED_CHECKSUM:
        raise AssertionError(f"checksum {checksum} != {EXPECTED_CHECKSUM}")
    return {
        "impl": IMPL,
        "n_obs": N_OBS,
        "n_positions": N_POSITIONS,
        "checksum": checksum,
        "pnl_identity_ok": True,
        "wall_ms": wall_ms,
        "acceptance": run_acceptance_matrix(acceptance_n_positions, acceptance_n_obs),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a single JSON object (wall_ms / RSS / scenarios/sec recorded, not SLA-gated).",
    )
    parser.add_argument(
        "--acceptance-n",
        type=int,
        default=ACCEPTANCE_N_POSITIONS,
        help="Acceptance N (trades). PR default 10; do not use 1000 in CI.",
    )
    parser.add_argument(
        "--acceptance-s",
        type=int,
        default=ACCEPTANCE_N_OBS,
        help="Acceptance S (scenarios). PR default 50; do not use 1000 in CI.",
    )
    args = parser.parse_args(argv)
    if args.acceptance_n < 1 or args.acceptance_s < 1:
        raise SystemExit("acceptance N and S must be positive")
    payload = run_full_reval_identity(
        acceptance_n_positions=args.acceptance_n,
        acceptance_n_obs=args.acceptance_s,
    )
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        acc = payload["acceptance"]
        print(
            "full-reval benchmark identity ok",
            payload["checksum"],
            f"n_obs={payload['n_obs']}",
            f"impl={payload['impl']}",
            f"acceptance={acc['n_positions']}x{acc['n_obs']}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
