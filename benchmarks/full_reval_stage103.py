#!/usr/bin/env python3
"""Stage 10.3 FULL_REVALUATION matrix harness (not a host / HTTP / kernel SLA).

Deterministic multi-asset book (cash equities + European options) on a fixture
snapshot and a seeded per-factor synthetic panel. Measures the product
``full_revaluation_pnl_from_panel`` / ``approximate_pnl_from_panel`` paths.

Shock unit / sensitivity / sign match historical FULL_REVALUATION:
equity/FX relative return, vol relative level, rates unused on this book
(spot/vol panel only). P&L = shocked PV − base PV; loss = −P&L.
Base market is a fixture snapshot, not live marks.
Reconciliation: SHA-256 of rounded P&L; builtin vs QuantLib allclose at
option-match rtol=2e-3. Same seed/spec reproduces the same checksum.

Do not invoke the M6 kernel SLA checker. Do not treat wall_ms,
scenarios/sec, or RSS as floors. SLA-K1/K2 are unchanged / post-R0.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import platform
import resource
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

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
    VaRMethodology,
)
from app.pricing.builtin import BuiltinPricingEngine  # noqa: E402
from app.risk.factor_panel import create_synthetic_factor_panel  # noqa: E402
from app.risk.factor_types import EquitySpot, EquityVol  # noqa: E402
from app.risk.historical import (  # noqa: E402
    approximate_pnl_from_panel,
    full_revaluation_pnl_from_panel,
)
from app.risk.scenarios import (  # noqa: E402
    historical_market_scenarios_from_panel,
    iter_shocked_snapshots,
)

SEED = 103
SMOKE_N_TRADES = 4
SMOKE_N_SCENARIOS = 8
OPTION_MATCH_RTOL = 2e-3
AS_OF = date(2026, 8, 6)
SYMBOLS = ("AAPL", "MSFT", "NVDA")
SPOTS = {"AAPL": 180.0, "MSFT": 420.0, "NVDA": 120.0}
VOLS = {"AAPL": 0.25, "MSFT": 0.22, "NVDA": 0.40}
DIVS = {sym: 0.01 for sym in SYMBOLS}
RATE = 0.04
_TRUTHY = {"1", "true", "yes", "on"}

MATRIX_SPEC: tuple[dict[str, Any], ...] = (
    {
        "n_trades": 100,
        "n_scenarios": 250,
        "methodology": "FULL_REVALUATION",
        "engines": ("builtin", "quantlib"),
    },
    {
        "n_trades": 100,
        "n_scenarios": 1000,
        "methodology": "FULL_REVALUATION",
        "engines": ("builtin", "quantlib"),
    },
    {
        "n_trades": 1000,
        "n_scenarios": 250,
        "methodology": "FULL_REVALUATION",
        "engines": ("builtin", "quantlib"),
    },
    {
        "n_trades": 1000,
        "n_scenarios": 1000,
        "methodology": "FULL_REVALUATION",
        "engines": ("builtin", "quantlib"),
    },
    {
        "n_trades": 10000,
        "n_scenarios": 1000,
        "methodology": "LINEAR",
        "engines": ("builtin",),
    },
    {
        "n_trades": 10000,
        "n_scenarios": 1000,
        "methodology": "DELTA_GAMMA",
        "engines": ("builtin",),
    },
)

NON_CLAIMS = (
    "Not an HTTP SLA. Not multi-tenant capacity. Not production throughput.",
    "Labeled-runner SLA-K1/K2 unchanged / post-R0; do not run the M6 kernel SLA checker here.",
    "Wall time, RSS, and scenarios/sec are recorded host observations, not floors.",
    "Synthetic fixture snapshot and seeded panel — not vendor market data.",
)


@dataclass(frozen=True, slots=True)
class Workload:
    portfolio: Portfolio
    market: MarketSnapshot
    panel: object
    seed: int
    n_trades: int
    n_scenarios: int


def _quantlib_required() -> bool:
    return os.environ.get("RISKFORGE_REQUIRE_QUANTLIB", "").strip().lower() in _TRUTHY


def _peak_rss_kib() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    rss = float(usage.ru_maxrss)
    if sys.platform == "darwin":
        return rss / 1024.0
    return rss


def _scenarios_per_sec(n_obs: int, wall_ms: float) -> float:
    elapsed_s = float(wall_ms) / 1000.0
    if elapsed_s <= 0.0:
        return 0.0
    return float(n_obs) / elapsed_s


def pnl_checksum(pnl: np.ndarray) -> str:
    lines = "\n".join(f"{x:.12f}" for x in np.asarray(pnl, dtype=float))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def build_multi_asset_workload(
    n_trades: int, n_scenarios: int, seed: int = SEED
) -> Workload:
    """Seeded cash-equity + option book so FULL_REVALUATION ≠ LINEAR."""
    if n_trades < 1 or n_scenarios < 1:
        raise ValueError("n_trades and n_scenarios must be positive")
    rng = np.random.default_rng(seed)
    n_options = max(1, n_trades // 4)
    n_equity = n_trades - n_options
    positions: list[EquityPosition | EuropeanOptionPosition] = []
    for i in range(n_equity):
        sym = SYMBOLS[i % len(SYMBOLS)]
        qty = float(int(rng.integers(1, 21)))
        positions.append(
            EquityPosition(
                type="equity",
                id=f"eq{i:05d}",
                symbol=sym,
                quantity=qty,
            )
        )
    for j in range(n_options):
        idx = n_equity + j
        sym = SYMBOLS[j % len(SYMBOLS)]
        qty = float(int(rng.integers(1, 11)))
        strike = SPOTS[sym]
        positions.append(
            EuropeanOptionPosition(
                type="european_option",
                id=f"opt{idx:05d}",
                symbol=sym,
                quantity=qty,
                strike=strike,
                maturity_years=1.0,
                option_type="call" if j % 2 == 0 else "put",
            )
        )
    book = Portfolio(
        id="stage103-multi-asset",
        name="stage103-multi-asset",
        positions=positions,
    )
    market = MarketSnapshot(
        id="stage103-fixture",
        as_of=AS_OF,
        equity_spots=dict(SPOTS),
        equity_vols=dict(VOLS),
        rates={"USD": RATE},
        dividend_yields=dict(DIVS),
    )
    factors = []
    for sym in SYMBOLS:
        factors.append(EquitySpot(sym))
        factors.append(EquityVol(underlying=sym))
    panel = create_synthetic_factor_panel(
        seed=seed, observations=n_scenarios, factors=factors, start=AS_OF
    )
    return Workload(
        portfolio=book,
        market=market,
        panel=panel,
        seed=seed,
        n_trades=n_trades,
        n_scenarios=n_scenarios,
    )


def _make_engine(engine_name: str):
    if engine_name == "builtin":
        return BuiltinPricingEngine()
    if engine_name != "quantlib":
        raise ValueError(f"unknown engine {engine_name!r}")
    from app.pricing.quantlib import QuantLibPricingEngine, QuantLibUnavailableError

    try:
        return QuantLibPricingEngine(evaluation_date=AS_OF)
    except QuantLibUnavailableError:
        raise


def _try_make_engine(engine_name: str) -> tuple[Any, str | None]:
    if engine_name == "builtin":
        return _make_engine("builtin"), None
    try:
        from app.pricing.quantlib import QuantLibUnavailableError
    except ImportError as exc:
        if _quantlib_required():
            raise RuntimeError(
                "QuantLib is required (RISKFORGE_REQUIRE_QUANTLIB=1) but could not "
                "be imported."
            ) from exc
        return None, "QuantLib is not installed"
    try:
        return _make_engine("quantlib"), None
    except QuantLibUnavailableError as exc:
        if _quantlib_required():
            raise
        return None, str(exc) or "QuantLib is not installed"


def _methodology(name: str) -> VaRMethodology:
    return VaRMethodology(name)


def _compute_pnl(workload: Workload, methodology: str, pricing) -> np.ndarray:
    meth = _methodology(methodology)
    if meth is VaRMethodology.FULL_REVALUATION:
        return full_revaluation_pnl_from_panel(
            workload.portfolio, pricing, workload.market, workload.panel
        )
    return approximate_pnl_from_panel(
        workload.portfolio,
        pricing,
        workload.market,
        workload.panel,
        methodology=meth,
    )


def _cache_state(methodology: str) -> str:
    if methodology == "FULL_REVALUATION":
        return "valuation_lru_bypassed"
    return "greeks_once_at_base"


def run_methodology_cell(
    workload: Workload,
    *,
    methodology: str,
    engine_name: str,
    warm: bool = True,
) -> dict[str, Any]:
    pricing, skip = _try_make_engine(engine_name)
    n_obs = workload.n_scenarios
    base = {
        "engine": engine_name,
        "methodology": methodology,
        "n_trades": workload.n_trades,
        "n_scenarios": n_obs,
        "seed": workload.seed,
        "worker_count": 1,
        "cache_state": _cache_state(methodology),
    }
    if pricing is None:
        return {**base, "available": False, "skip_reason": skip, "status": "skipped"}

    rss_before = _peak_rss_kib()
    started = time.perf_counter()
    pnl_cold = _compute_pnl(workload, methodology, pricing)
    wall_ms_cold = (time.perf_counter() - started) * 1000.0
    rss_cold = max(rss_before, _peak_rss_kib())
    if pnl_cold.shape != (n_obs,):
        raise AssertionError(f"n_obs {pnl_cold.shape} != {(n_obs,)}")

    wall_ms_warm = wall_ms_cold
    pnl_warm = pnl_cold
    rss_warm = rss_cold
    if warm:
        rss_w0 = _peak_rss_kib()
        started_w = time.perf_counter()
        pnl_warm = _compute_pnl(workload, methodology, pricing)
        wall_ms_warm = (time.perf_counter() - started_w) * 1000.0
        rss_warm = max(rss_w0, _peak_rss_kib())
        if not np.allclose(pnl_warm, pnl_cold, atol=1e-12):
            raise AssertionError("warm P&L differs from cold P&L")

    return {
        **base,
        "available": True,
        "status": "ok",
        "checksum": pnl_checksum(pnl_cold),
        "pnl": pnl_cold,
        "wall_ms": wall_ms_cold,
        "wall_ms_cold": wall_ms_cold,
        "wall_ms_warm": wall_ms_warm,
        "peak_rss_kib": max(rss_cold, rss_warm),
        "scenarios_per_sec": _scenarios_per_sec(n_obs, wall_ms_cold),
    }


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    published = dict(row)
    published.pop("pnl", None)
    return published


def environment_metadata(*, worker_count: int = 1) -> dict[str, Any]:
    numpy_version: str | None
    try:
        numpy_version = np.__version__
    except Exception:
        numpy_version = None
    ql_version = None
    try:
        import QuantLib as ql

        ql_version = getattr(ql, "__version__", None)
    except ImportError:
        ql_version = None
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "numpy": numpy_version,
        "quantlib": ql_version,
        "logical_cpus": os.cpu_count(),
        "worker_count": worker_count,
        "kernel_threads": os.environ.get("RISKFORGE_KERNEL_THREADS"),
        "pricing_engine_env": os.environ.get("RISKFORGE_PRICING_ENGINE"),
        "note": (
            "In-process worker_count=1. QuantLib is process-serialized (ADR 007). "
            "Not an HTTP SLA; SLA-K1/K2 unchanged/post-R0."
        ),
    }


def profile_phases(workload: Workload, engine_name: str = "builtin") -> dict[str, float]:
    """Coarse phase split. Diagnostic only; cell wall uses the product path."""
    t0 = time.perf_counter()
    scenarios = historical_market_scenarios_from_panel(workload.panel)
    scenario_ms = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    snaps = list(iter_shocked_snapshots(workload.market, scenarios))
    snapshot_ms = (time.perf_counter() - t0) * 1000.0
    if len(snaps) != workload.n_scenarios:
        raise AssertionError("snapshot count != n_scenarios")

    t0 = time.perf_counter()
    pricing, skip = _try_make_engine(engine_name)
    engine_ms = (time.perf_counter() - t0) * 1000.0
    if pricing is None:
        return {
            "scenario_construction_ms": scenario_ms,
            "snapshot_transform_ms": snapshot_ms,
            "engine_construction_ms": engine_ms,
            "pricing_ms": float("nan"),
            "persistence_ms": 0.0,
            "aggregation_ms": 0.0,
            "skip_reason": skip,
        }

    t0 = time.perf_counter()
    pnl = full_revaluation_pnl_from_panel(
        workload.portfolio, pricing, workload.market, workload.panel
    )
    pricing_ms = (time.perf_counter() - t0) * 1000.0

    t0 = time.perf_counter()
    _ = float(np.sum(pnl))
    checksum = pnl_checksum(pnl)
    aggregation_ms = (time.perf_counter() - t0) * 1000.0
    if not checksum:
        raise AssertionError("empty checksum")

    return {
        "scenario_construction_ms": scenario_ms,
        "snapshot_transform_ms": snapshot_ms,
        "engine_construction_ms": engine_ms,
        "pricing_ms": pricing_ms,
        "persistence_ms": 0.0,
        "aggregation_ms": aggregation_ms,
    }


def _pnl_gap(builtin_pnl: np.ndarray, quantlib_pnl: np.ndarray) -> dict[str, Any]:
    builtin_pnl = np.asarray(builtin_pnl, dtype=float)
    quantlib_pnl = np.asarray(quantlib_pnl, dtype=float)
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
        "within_tolerance": within,
        "within_option_match_rtol": within,
    }


def run_parity_gate(
    n_trades: int = SMOKE_N_TRADES,
    n_scenarios: int = SMOKE_N_SCENARIOS,
    seed: int = SEED,
) -> dict[str, Any]:
    workload = build_multi_asset_workload(n_trades, n_scenarios, seed=seed)
    builtin = run_methodology_cell(
        workload, methodology="FULL_REVALUATION", engine_name="builtin"
    )
    quantlib = run_methodology_cell(
        workload, methodology="FULL_REVALUATION", engine_name="quantlib"
    )
    if not quantlib.get("available"):
        raise RuntimeError(quantlib.get("skip_reason") or "QuantLib unavailable")
    gap = _pnl_gap(builtin["pnl"], quantlib["pnl"])
    if not gap["within_tolerance"]:
        raise AssertionError(
            "builtin vs QuantLib FULL_REVALUATION P&L exceeds option-match "
            f"rtol={OPTION_MATCH_RTOL}: {gap}"
        )
    return {
        "n_trades": n_trades,
        "n_scenarios": n_scenarios,
        "seed": seed,
        "builtin_checksum": builtin["checksum"],
        "quantlib_checksum": quantlib["checksum"],
        **gap,
    }


def run_smoke() -> dict[str, Any]:
    workload = build_multi_asset_workload(SMOKE_N_TRADES, SMOKE_N_SCENARIOS, seed=SEED)
    profile = profile_phases(workload, "builtin")
    builtin = run_methodology_cell(
        workload, methodology="FULL_REVALUATION", engine_name="builtin"
    )
    quantlib = run_methodology_cell(
        workload, methodology="FULL_REVALUATION", engine_name="quantlib"
    )
    payload: dict[str, Any] = {
        "kind": "stage103_smoke",
        "n_trades": SMOKE_N_TRADES,
        "n_scenarios": SMOKE_N_SCENARIOS,
        "seed": SEED,
        "methodology": "FULL_REVALUATION",
        "builtin": _public_row(builtin),
        "quantlib": _public_row(quantlib),
        "profile": {k: v for k, v in profile.items() if k != "skip_reason"},
        "environment": environment_metadata(),
        "non_claims": list(NON_CLAIMS),
        "quant_contract": {
            "shock_unit": "EquitySpot/FXSpot relative return; EquityVol relative vol level",
            "sensitivity": "FULL_REVALUATION reprice; LINEAR/DELTA_GAMMA engine Greeks",
            "sign": "P&L = shocked PV − base PV; loss = −P&L",
            "base_market": "fixture snapshot stage103-fixture, not live marks",
            "reconciliation": f"checksum + builtin vs QuantLib allclose rtol={OPTION_MATCH_RTOL}",
        },
    }
    if builtin.get("available") and quantlib.get("available"):
        payload["parity"] = _pnl_gap(builtin["pnl"], quantlib["pnl"])
        if not payload["parity"]["within_tolerance"]:
            raise AssertionError(f"smoke parity failed: {payload['parity']}")
    return payload


def _unavailable_cell(
    spec: dict[str, Any], engine_name: str, reason: str, status: str
) -> dict[str, Any]:
    return {
        "engine": engine_name,
        "methodology": spec["methodology"],
        "n_trades": spec["n_trades"],
        "n_scenarios": spec["n_scenarios"],
        "seed": SEED,
        "worker_count": 1,
        "cache_state": _cache_state(spec["methodology"]),
        "available": False,
        "status": status,
        "skip_reason": reason,
    }


def run_isolated_cell(
    n_trades: int,
    n_scenarios: int,
    methodology: str,
    engine_name: str,
    *,
    seed: int = SEED,
    warm: bool = True,
) -> dict[str, Any]:
    """Child entry: one matrix cell in this process for isolated RSS / timeout."""
    workload = build_multi_asset_workload(n_trades, n_scenarios, seed=seed)
    row = run_methodology_cell(
        workload, methodology=methodology, engine_name=engine_name, warm=warm
    )
    published = _public_row(row)
    published["rss_isolated"] = True
    published["rss_pid"] = os.getpid()
    return published


def run_matrix_cell(
    spec: dict[str, Any],
    engine_name: str,
    *,
    max_cell_wall_s: float | None,
    warm: bool,
) -> dict[str, Any]:
    payload = {
        "n_trades": spec["n_trades"],
        "n_scenarios": spec["n_scenarios"],
        "methodology": spec["methodology"],
        "engine": engine_name,
        "seed": SEED,
        "warm": warm,
    }
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--isolated-cell",
        json.dumps(payload, sort_keys=True),
    ]
    timeout = None if max_cell_wall_s is None or max_cell_wall_s <= 0 else float(max_cell_wall_s)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
            env={**os.environ, "PYTHONPATH": str(BACKEND_ROOT)},
        )
    except subprocess.TimeoutExpired:
        return {
            **_unavailable_cell(
                spec,
                engine_name,
                f"aborted after {timeout}s wall budget (not an SLA; cell too slow on this host)",
                "aborted_too_slow",
            ),
            "budget_s": timeout,
            "rss_isolated": True,
        }
    if proc.returncode != 0:
        raise RuntimeError(
            f"isolated {engine_name} {spec['methodology']} "
            f"{spec['n_trades']}x{spec['n_scenarios']} failed "
            f"(exit {proc.returncode}): {proc.stderr}"
        )
    row = json.loads(proc.stdout)
    if timeout is not None and row.get("status") == "ok":
        wall_s = float(row.get("wall_ms", 0.0)) / 1000.0
        if wall_s > timeout:
            row["status"] = "completed_over_budget"
            row["budget_s"] = timeout
    return row


def run_matrix(
    *,
    max_cell_wall_s: float | None = 180.0,
    skip_quantlib: bool = False,
    cells: tuple[dict[str, Any], ...] | None = None,
) -> dict[str, Any]:
    """Attempt the Stage 10.3 matrix. Slow cells are recorded, not rewritten."""
    results: list[dict[str, Any]] = []
    specs = cells or MATRIX_SPEC
    for spec in specs:
        engines = spec["engines"]
        if skip_quantlib:
            engines = tuple(e for e in engines if e != "quantlib")
        for engine_name in engines:
            if engine_name == "quantlib" and skip_quantlib:
                results.append(
                    _unavailable_cell(spec, engine_name, "skipped by --skip-quantlib", "skipped")
                )
                continue
            try:
                row = run_matrix_cell(
                    spec,
                    engine_name,
                    max_cell_wall_s=max_cell_wall_s,
                    warm=spec["n_trades"] * spec["n_scenarios"] <= 100 * 1000,
                )
            except Exception as exc:  # noqa: BLE001 — record honest failure
                results.append(
                    {
                        **_unavailable_cell(spec, engine_name, str(exc), "failed"),
                        "error_type": type(exc).__name__,
                    }
                )
                continue
            if (
                max_cell_wall_s is not None
                and row.get("status") == "ok"
                and float(row["wall_ms"]) / 1000.0 > max_cell_wall_s
            ):
                row = dict(row)
                row["status"] = "completed_over_budget"
                row["budget_s"] = max_cell_wall_s
            results.append(row)
    return {
        "kind": "stage103_matrix",
        "seed": SEED,
        "option_match_rtol": OPTION_MATCH_RTOL,
        "environment": environment_metadata(),
        "non_claims": list(NON_CLAIMS),
        "quant_contract": {
            "shock_unit": "EquitySpot relative return; EquityVol relative vol level",
            "sign": "P&L = shocked PV − base PV; loss = −P&L",
            "base_market": "fixture snapshot, not live marks",
            "reconciliation": "P&L checksum; builtin vs QuantLib rtol=2e-3; same seed reproduces",
        },
        "profile_smoke": profile_phases(
            build_multi_asset_workload(SMOKE_N_TRADES, SMOKE_N_SCENARIOS, seed=SEED)
        ),
        "profile_100x250": profile_phases(
            build_multi_asset_workload(100, 250, seed=SEED)
        ),
        "results": results,
    }


def csv_rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if payload.get("kind") == "stage103_smoke":
        for engine_key in ("builtin", "quantlib"):
            row = payload.get(engine_key) or {}
            if not row:
                continue
            rows.append(
                {
                    "kind": payload["kind"],
                    "methodology": payload.get("methodology", ""),
                    "n_trades": payload.get("n_trades", ""),
                    "n_scenarios": payload.get("n_scenarios", ""),
                    "engine": row.get("engine", engine_key),
                    "status": row.get("status", ""),
                    "available": row.get("available", ""),
                    "wall_ms": row.get("wall_ms", ""),
                    "wall_ms_cold": row.get("wall_ms_cold", ""),
                    "wall_ms_warm": row.get("wall_ms_warm", ""),
                    "peak_rss_kib": row.get("peak_rss_kib", ""),
                    "scenarios_per_sec": row.get("scenarios_per_sec", ""),
                    "worker_count": row.get("worker_count", ""),
                    "cache_state": row.get("cache_state", ""),
                    "checksum": row.get("checksum", ""),
                    "skip_reason": row.get("skip_reason", ""),
                }
            )
        return rows
    for row in payload.get("results") or []:
        rows.append(
            {
                "kind": payload.get("kind", "stage103_matrix"),
                "methodology": row.get("methodology", ""),
                "n_trades": row.get("n_trades", ""),
                "n_scenarios": row.get("n_scenarios", ""),
                "engine": row.get("engine", ""),
                "status": row.get("status", ""),
                "available": row.get("available", ""),
                "wall_ms": row.get("wall_ms", ""),
                "wall_ms_cold": row.get("wall_ms_cold", ""),
                "wall_ms_warm": row.get("wall_ms_warm", ""),
                "peak_rss_kib": row.get("peak_rss_kib", ""),
                "scenarios_per_sec": row.get("scenarios_per_sec", ""),
                "worker_count": row.get("worker_count", ""),
                "cache_state": row.get("cache_state", ""),
                "checksum": row.get("checksum", ""),
                "skip_reason": row.get("skip_reason", ""),
            }
        )
    return rows


def write_csv(payload: dict[str, Any], path: Path) -> None:
    rows = csv_rows_from_payload(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "kind",
        "methodology",
        "n_trades",
        "n_scenarios",
        "engine",
        "status",
        "available",
        "wall_ms",
        "wall_ms_cold",
        "wall_ms_warm",
        "peak_rss_kib",
        "scenarios_per_sec",
        "worker_count",
        "cache_state",
        "checksum",
        "skip_reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _fmt(value: object) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        if value >= 1000:
            return f"{value:.1f}"
        return f"{value:.3f}"
    return str(value)


def render_markdown(payload: dict[str, Any]) -> str:
    env = payload.get("environment") or {}
    lines = [
        "# Stage 10.3 FULL_REVALUATION results",
        "",
        "Host observations for the product FULL_REVALUATION / LINEAR / DELTA_GAMMA",
        "paths on a seeded multi-asset fixture. **Not a host SLA. Not an HTTP SLA.**",
        "Labeled-runner **SLA-K1/K2 unchanged / post-R0**.",
        "",
        "## Non-claims",
        "",
    ]
    for claim in payload.get("non_claims") or NON_CLAIMS:
        lines.append(f"- {claim}")
    lines.extend(
        [
            "",
            "## Quant contract",
            "",
            "- Shock unit: EquitySpot relative return (`0.01` = +1%); EquityVol relative vol level.",
            "- Sign: P&L = shocked PV − base PV; loss = −P&L.",
            "- Base market: fixture snapshot `stage103-fixture`, not live marks.",
            f"- Reconciliation: P&L checksum; builtin vs QuantLib allclose rtol={OPTION_MATCH_RTOL}.",
            "- Synthetic seeded panel — not vendor data. Methodology is not switched to look faster.",
            "",
            "## Environment",
            "",
            f"- platform: `{env.get('platform', '')}`",
            f"- machine: `{env.get('machine', '')}`",
            f"- python: `{env.get('python', '')}` numpy `{env.get('numpy', '')}` QuantLib `{env.get('quantlib', '')}`",
            f"- logical CPUs: {env.get('logical_cpus', '')}; in-process worker_count={env.get('worker_count', 1)}",
            f"- note: {env.get('note', '')}",
            "",
        ]
    )
    profile = payload.get("profile") or payload.get("profile_smoke") or {}
    if profile:
        lines.extend(
            [
                "## Coarse profile",
                "",
                "Smoke (4×8) is too small for pricing to dominate: scenario/snapshot",
                "construction can exceed the product reprice. At 100×250 (same seed/book",
                "family) pricing is the bottleneck. Persistence is not in this harness (0 ms).",
                "Timed cells use the product iterator (no second materialized snapshot list).",
                "LINEAR/DELTA_GAMMA stay on `approximate_pnl_from_panel` — the native scenario",
                "kernel is not swapped in to look faster. No product-code rewrite: C++ / API",
                "pricing paths are out of this lane, and methodology is unchanged.",
                "",
            ]
        )
        lines.extend(
            [
                "### Smoke 4×8",
                "",
                "| Phase | ms |",
                "|---|---:|",
                f"| scenario construction | {_fmt(profile.get('scenario_construction_ms'))} |",
                f"| snapshot transforms | {_fmt(profile.get('snapshot_transform_ms'))} |",
                f"| engine construction | {_fmt(profile.get('engine_construction_ms'))} |",
                f"| pricing (product path) | {_fmt(profile.get('pricing_ms'))} |",
                f"| persistence | {_fmt(profile.get('persistence_ms'))} |",
                f"| aggregation / checksum | {_fmt(profile.get('aggregation_ms'))} |",
                "",
            ]
        )
        profile_mid = payload.get("profile_100x250") or {}
        if profile_mid:
            lines.extend(
                [
                    "### 100×250 FULL_REVALUATION builtin (same fixture family)",
                    "",
                    "| Phase | ms |",
                    "|---|---:|",
                    f"| scenario construction | {_fmt(profile_mid.get('scenario_construction_ms'))} |",
                    f"| snapshot transforms | {_fmt(profile_mid.get('snapshot_transform_ms'))} |",
                    f"| engine construction | {_fmt(profile_mid.get('engine_construction_ms'))} |",
                    f"| pricing (product path) | {_fmt(profile_mid.get('pricing_ms'))} |",
                    f"| persistence | {_fmt(profile_mid.get('persistence_ms'))} |",
                    f"| aggregation / checksum | {_fmt(profile_mid.get('aggregation_ms'))} |",
                    "",
                ]
            )
    rows = csv_rows_from_payload(payload)
    lines.extend(
        [
            "## Scaling table",
            "",
            "| N trades | S scenarios | methodology | engine | status | wall_ms | wall_ms_warm | peak_rss_kib | scenarios/sec | workers | cache | checksum |",
            "|---:|---:|---|---|---|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in rows:
        lines.append(
            "| {n_trades} | {n_scenarios} | {methodology} | {engine} | {status} | {wall_ms} | {wall_ms_warm} | {peak_rss_kib} | {scenarios_per_sec} | {worker_count} | {cache_state} | `{checksum}` |".format(
                n_trades=row.get("n_trades", ""),
                n_scenarios=row.get("n_scenarios", ""),
                methodology=row.get("methodology", ""),
                engine=row.get("engine", ""),
                status=row.get("status", ""),
                wall_ms=_fmt(row.get("wall_ms")),
                wall_ms_warm=_fmt(row.get("wall_ms_warm")),
                peak_rss_kib=_fmt(row.get("peak_rss_kib")),
                scenarios_per_sec=_fmt(row.get("scenarios_per_sec")),
                worker_count=row.get("worker_count", ""),
                cache_state=row.get("cache_state", ""),
                checksum=row.get("checksum") or row.get("skip_reason") or "",
            )
        )
    chart_rows = [
        r
        for r in rows
        if r.get("status") in {"ok", "completed_over_budget"} and r.get("wall_ms") not in ("", None)
    ]
    if chart_rows:
        lines.extend(
            [
                "",
                "## Chart (generated from JSON)",
                "",
                "Wall times below are copied from the JSON/CSV rows. Not hand-drawn.",
                "",
            ]
        )
        for row in chart_rows:
            label = f"{row['n_trades']}×{row['n_scenarios']} {row['methodology']} {row['engine']}"
            lines.append(f"- `{label}`: {_fmt(row['wall_ms'])} ms")
    lines.extend(
        [
            "",
            "Warm vs cold is recorded when N×S ≤ 100×1000; larger cells record cold only",
            "(same checksum path). QuantLib warm can be slower than cold on this host —",
            "that is left as observed, not smoothed.",
            "",
            "R0.6 identity benches in `run_full_reval_bench.py` are unchanged.",
            "",
        ]
    )
    return "\n".join(lines)


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(payload), encoding="utf-8")


def cli_stage103(
    *,
    smoke: bool,
    emit_json: bool,
    csv_path: Path | None,
    markdown_path: Path | None,
    max_cell_wall_s: float | None,
    skip_quantlib: bool,
) -> dict[str, Any]:
    if smoke:
        payload = run_smoke()
    else:
        payload = run_matrix(max_cell_wall_s=max_cell_wall_s, skip_quantlib=skip_quantlib)
    if csv_path is not None:
        write_csv(payload, csv_path)
    if markdown_path is not None:
        write_markdown(payload, markdown_path)
    if emit_json:
        print(json.dumps(payload, sort_keys=True, default=str))
    else:
        print(render_markdown(payload))
    return payload


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--isolated-cell",
        default=None,
        help="Child mode: JSON object with n_trades, n_scenarios, methodology, engine, seed, warm.",
    )
    args = parser.parse_args(argv)
    if args.isolated_cell:
        spec = json.loads(args.isolated_cell)
        row = run_isolated_cell(
            int(spec["n_trades"]),
            int(spec["n_scenarios"]),
            str(spec["methodology"]),
            str(spec["engine"]),
            seed=int(spec.get("seed", SEED)),
            warm=bool(spec.get("warm", True)),
        )
        print(json.dumps(row, sort_keys=True, default=str))
        return 0
    raise SystemExit("use benchmarks/run_full_reval_bench.py --stage103")


if __name__ == "__main__":
    raise SystemExit(_main())
