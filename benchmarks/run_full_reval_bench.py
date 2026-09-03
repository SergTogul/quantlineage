#!/usr/bin/env python3
"""R0.6.1 / RF-007 — FULL_REVALUATION baseline identity bench (not a host SLA).

Reuses the nightly 120-obs unit-equity sample
(``backend/tests/test_nightly_full_reval_sample.py``): shocked PV − base PV.
Emits JSON with ``impl``, ``n_obs``, and a SHA-256 checksum of the rounded
P&L vector. Wall time is recorded for operators but is **not** an SLA: do
not treat a recorded wall time or positive throughput as a floor.

Do not invoke ``benchmarks/check_m6_sla.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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
N_OBS = 120
N_POSITIONS = 1
QUANTITY = 10.0
SPOT = 100.0
# SHA-256 of rounded engine P&L lines (allclose 1e-12 to 10 * 100 * linspace(-0.05, 0.05, 120)).
EXPECTED_CHECKSUM = "6602fa6906f2579f5c89af72a41ab274c07650234fff69387bc2202b5a40534f"


def bench_book() -> tuple[Portfolio, MarketSnapshot, ArrayHistoricalDataset]:
    pos = EquityPosition(type="equity", id="eq", symbol="UNIT", quantity=QUANTITY, price=SPOT)
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


def pnl_checksum(pnl: np.ndarray) -> str:
    lines = "\n".join(f"{x:.12f}" for x in pnl)
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def run_full_reval_identity() -> dict:
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
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a single JSON object (wall_ms recorded, not SLA-gated).",
    )
    args = parser.parse_args(argv)
    payload = run_full_reval_identity()
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            "full-reval benchmark identity ok",
            payload["checksum"],
            f"n_obs={payload['n_obs']}",
            f"impl={payload['impl']}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
