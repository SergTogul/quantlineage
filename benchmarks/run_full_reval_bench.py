#!/usr/bin/env python3
"""R0.6.1 / R0.6.7 / R0.6.8 / RF-007 — FULL_REVALUATION identity + acceptance benches (not a host SLA).

Reuses the nightly 120-obs unit-equity sample
(``backend/tests/test_nightly_full_reval_sample.py``): shocked PV − base PV.
Emits JSON with ``impl``, ``n_obs``, and a SHA-256 checksum of the rounded
P&L vector. Wall time is recorded for operators but is **not** an SLA: do
not treat a recorded wall time, RSS, or scenarios/sec as a floor.

R0.6.7 acceptance (PR-safe default N=10 × S=50, above 1×120) records peak
RSS, scenarios/sec, builtin vs QuantLib at the same N×S, and warm vs cold
``wall_ms`` on the same fixture.

R0.6.8 reconstruction uses a European option book (spot/vol/rate/div live),
pins checksums per engine, measures peak RSS in a subprocess per impl, and
records the builtin vs QuantLib P&L gap at the existing option-match
``rel=2e-3``. QuantLib is skip-or-run (fail-closed when
``RISKFORGE_REQUIRE_QUANTLIB=1``). Do not invoke ``benchmarks/check_m6_sla.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.models import (  # noqa: E402
    EquityPosition,
    EuropeanOptionPosition,
    MarketSnapshot,
    Portfolio,
)
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

RECONSTRUCTION_N_POSITIONS = 10
RECONSTRUCTION_N_OBS = 50
RECONSTRUCTION_STRIKE = 100.0
RECONSTRUCTION_VOL = 0.20
RECONSTRUCTION_RATE = 0.03
RECONSTRUCTION_DIV = 0.01
RECONSTRUCTION_MATURITY = 1.0
RECONSTRUCTION_AS_OF = date(2026, 9, 1)
OPTION_MATCH_RTOL = 2e-3
# SHA-256 of rounded reconstruction P&L (European options; not qty*spot).
# Option P&L SHAs are host/libm-specific at 12 decimals. Record checksums;
# do not pin them as a cross-platform gate (Linux CI ≠ Darwin).

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


def reconstruction_book(
    n_positions: int, n_obs: int
) -> tuple[Portfolio, MarketSnapshot, ArrayHistoricalDataset]:
    """European option book with live spot / vol / rate / dividend marks."""
    positions = [
        EuropeanOptionPosition(
            type="european_option",
            id=f"opt{i:02d}",
            symbol=f"UNIT_{i:02d}",
            quantity=QUANTITY,
            strike=RECONSTRUCTION_STRIKE,
            maturity_years=RECONSTRUCTION_MATURITY,
            option_type="call",
        )
        for i in range(n_positions)
    ]
    book = Portfolio(id="r068-reconstruction", name="r068", positions=positions)
    symbols = [f"UNIT_{i:02d}" for i in range(n_positions)]
    market = MarketSnapshot(
        id="base",
        as_of=RECONSTRUCTION_AS_OF,
        equity_spots={sym: SPOT for sym in symbols},
        equity_vols={sym: RECONSTRUCTION_VOL for sym in symbols},
        rates={"USD": RECONSTRUCTION_RATE},
        dividend_yields={sym: RECONSTRUCTION_DIV for sym in symbols},
    )
    equity_returns = np.linspace(-0.05, 0.05, n_obs)
    vol_moves = np.linspace(-0.10, 0.10, n_obs)
    rate_moves_bps = np.linspace(-12.0, 12.0, n_obs)
    zeros = np.zeros(n_obs)
    dataset = ArrayHistoricalDataset(
        FactorObservationSeries(
            equity_returns=equity_returns,
            vol_moves=vol_moves,
            rate_moves_bps=rate_moves_bps,
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


def _quantlib_unavailable_row(n_positions: int, n_obs: int, reason: str) -> dict:
    return {
        "impl": IMPL_QUANTLIB,
        "n_positions": n_positions,
        "n_obs": n_obs,
        "available": False,
        "rss_isolated": True,
        "skip_reason": reason,
    }


def _reconstruction_row(
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
    cash_equity = float(n_positions) * QUANTITY * SPOT * dataset.factor_observations().equity_returns
    if np.allclose(pnl_cold, cash_equity, atol=1e-6):
        raise AssertionError("reconstruction P&L matches cash-equity quantity * spot; not an option book")
    if not np.allclose(pnl_warm, pnl_cold, atol=1e-12):
        raise AssertionError("warm P&L differs from cold P&L")
    checksum = pnl_checksum(pnl_cold)
    if (
        expected_checksum is not None
        and expected_checksum != "PENDING_LOCAL_PIN"
        and checksum != expected_checksum
    ):
        raise AssertionError(f"checksum {checksum} != {expected_checksum}")
    return {
        "impl": impl,
        "n_obs": n_obs,
        "n_positions": n_positions,
        "checksum": checksum,
        "pnl_identity_ok": True,
        "wall_ms": wall_ms_cold,
        "wall_ms_cold": wall_ms_cold,
        "wall_ms_warm": wall_ms_warm,
        "peak_rss_kib": max(rss_cold, rss_warm),
        "scenarios_per_sec": _scenarios_per_sec(n_obs, wall_ms_cold),
        "available": True,
        "rss_isolated": True,
        "rss_pid": os.getpid(),
        "pnl": [float(x) for x in pnl_cold],
    }


def run_isolated_reconstruction_impl(impl: str, n_positions: int, n_obs: int) -> dict:
    """Run one reconstruction engine in this process (child entry point)."""
    book, market, dataset = reconstruction_book(n_positions, n_obs)
    pin = None
    if impl == IMPL:
        pricing = BuiltinPricingEngine()
        return _reconstruction_row(
            impl=IMPL,
            n_positions=n_positions,
            n_obs=n_obs,
            pricing=pricing,
            book=book,
            market=market,
            dataset=dataset,
            expected_checksum=pin,
        )
    if impl != IMPL_QUANTLIB:
        raise SystemExit(f"unknown isolated impl {impl!r}")
    try:
        from app.pricing.quantlib import QuantLibPricingEngine, QuantLibUnavailableError
    except ImportError as exc:
        if _quantlib_required():
            raise RuntimeError(
                "QuantLib is required (RISKFORGE_REQUIRE_QUANTLIB=1) but could not "
                "be imported. Install backend/requirements.txt including QuantLib."
            ) from exc
        return _quantlib_unavailable_row(n_positions, n_obs, "QuantLib is not installed")
    try:
        pricing = QuantLibPricingEngine(evaluation_date=RECONSTRUCTION_AS_OF)
    except QuantLibUnavailableError as exc:
        if _quantlib_required():
            raise
        return _quantlib_unavailable_row(n_positions, n_obs, str(exc) or "QuantLib is not installed")
    return _reconstruction_row(
        impl=IMPL_QUANTLIB,
        n_positions=n_positions,
        n_obs=n_obs,
        pricing=pricing,
        book=book,
        market=market,
        dataset=dataset,
        expected_checksum=pin,
    )


def _spawn_isolated_impl(impl: str, n_positions: int, n_obs: int) -> dict:
    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--json",
            "--isolated-impl",
            impl,
            "--reconstruction-n",
            str(n_positions),
            "--reconstruction-s",
            str(n_obs),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"isolated {impl} reconstruction failed (exit {proc.returncode}): {proc.stderr}"
        )
    return json.loads(proc.stdout)


def _pnl_gap(builtin_row: dict, quantlib_row: dict) -> dict:
    builtin_pnl = np.asarray(builtin_row["pnl"], dtype=float)
    quantlib_pnl = np.asarray(quantlib_row["pnl"], dtype=float)
    abs_diff = np.abs(quantlib_pnl - builtin_pnl)
    denom = np.maximum(np.abs(builtin_pnl), 1e-12)
    rel = abs_diff / denom
    max_abs = float(abs_diff.max()) if abs_diff.size else 0.0
    max_rel = float(rel.max()) if rel.size else 0.0
    within = bool(np.allclose(quantlib_pnl, builtin_pnl, rtol=OPTION_MATCH_RTOL, atol=0.0))
    return {
        "max_abs": max_abs,
        "max_rel": max_rel,
        "rtol": OPTION_MATCH_RTOL,
        "within_option_match_rtol": within,
    }


def _public_reconstruction_row(row: dict) -> dict:
    published = dict(row)
    published.pop("pnl", None)
    return published


def run_reconstruction_matrix(n_positions: int, n_obs: int) -> dict:
    builtin = _spawn_isolated_impl(IMPL, n_positions, n_obs)
    quantlib = _spawn_isolated_impl(IMPL_QUANTLIB, n_positions, n_obs)
    payload = {
        "n_positions": n_positions,
        "n_obs": n_obs,
        "book": "european_option",
        "rss_isolated": True,
        "option_match_rtol": OPTION_MATCH_RTOL,
        "builtin": _public_reconstruction_row(builtin),
        "quantlib": _public_reconstruction_row(quantlib),
    }
    if builtin.get("available") and quantlib.get("available"):
        payload["pnl_gap"] = _pnl_gap(builtin, quantlib)
        if not payload["pnl_gap"]["within_option_match_rtol"]:
            raise AssertionError(
                "builtin vs QuantLib reconstruction P&L exceeds option-match "
                f"rtol={OPTION_MATCH_RTOL}: {payload['pnl_gap']}"
            )
    return payload


def run_full_reval_identity(
    *,
    acceptance_n_positions: int = ACCEPTANCE_N_POSITIONS,
    acceptance_n_obs: int = ACCEPTANCE_N_OBS,
    reconstruction_n_positions: int = RECONSTRUCTION_N_POSITIONS,
    reconstruction_n_obs: int = RECONSTRUCTION_N_OBS,
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
        "reconstruction": run_reconstruction_matrix(
            reconstruction_n_positions, reconstruction_n_obs
        ),
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
    parser.add_argument(
        "--reconstruction-n",
        type=int,
        default=RECONSTRUCTION_N_POSITIONS,
        help="Reconstruction N (option trades). PR default 10; nightly 100.",
    )
    parser.add_argument(
        "--reconstruction-s",
        type=int,
        default=RECONSTRUCTION_N_OBS,
        help="Reconstruction S (scenarios). PR default 50.",
    )
    parser.add_argument(
        "--isolated-impl",
        choices=(IMPL, IMPL_QUANTLIB),
        default=None,
        help="Child mode: run one reconstruction engine in this process for isolated RSS.",
    )
    parser.add_argument(
        "--reconstruction-only",
        action="store_true",
        help="Emit only the reconstruction matrix (used by the N=100 nightly job).",
    )
    args = parser.parse_args(argv)
    if args.acceptance_n < 1 or args.acceptance_s < 1:
        raise SystemExit("acceptance N and S must be positive")
    if args.reconstruction_n < 1 or args.reconstruction_s < 1:
        raise SystemExit("reconstruction N and S must be positive")
    if args.isolated_impl:
        payload = run_isolated_reconstruction_impl(
            args.isolated_impl, args.reconstruction_n, args.reconstruction_s
        )
    elif args.reconstruction_only:
        payload = run_reconstruction_matrix(args.reconstruction_n, args.reconstruction_s)
    else:
        payload = run_full_reval_identity(
            acceptance_n_positions=args.acceptance_n,
            acceptance_n_obs=args.acceptance_s,
            reconstruction_n_positions=args.reconstruction_n,
            reconstruction_n_obs=args.reconstruction_s,
        )
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    elif args.isolated_impl or args.reconstruction_only:
        print(
            "full-reval reconstruction ok",
            payload.get("checksum") or payload.get("builtin", {}).get("checksum"),
            f"n_positions={payload.get('n_positions', args.reconstruction_n)}",
            f"n_obs={payload.get('n_obs', args.reconstruction_s)}",
        )
    else:
        acc = payload["acceptance"]
        recon = payload["reconstruction"]
        print(
            "full-reval benchmark identity ok",
            payload["checksum"],
            f"n_obs={payload['n_obs']}",
            f"impl={payload['impl']}",
            f"acceptance={acc['n_positions']}x{acc['n_obs']}",
            f"reconstruction={recon['n_positions']}x{recon['n_obs']}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
