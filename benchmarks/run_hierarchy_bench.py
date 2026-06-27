#!/usr/bin/env python3
"""R0.12.4 / RF-016 — hierarchy identity benchmark (not a host SLA).

Builds a deterministic multi-desk equity book, runs ``HierarchyEngine.build``,
and emits JSON with node counts, additive-reconciliation flag, and a checksum
of rounded node metrics. Wall time is recorded for operators but is **not**
an SLA: do not treat a recorded wall time or positive throughput as a floor.

Nightly CI pins ``impl``, ``n_positions``, ``n_nodes``, ``market_value``, and
``checksum``. Do not invoke ``benchmarks/check_m6_sla.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.domain.models import EquityPosition, MarketSnapshot, Portfolio  # noqa: E402
from app.pricing.builtin import BuiltinPricingEngine  # noqa: E402
from app.risk.hierarchy import HierarchyEngine  # noqa: E402
from app.risk.historical import HistoricalRiskEngine  # noqa: E402

IMPL = "hierarchy_python"
SEED = 1
OBSERVATIONS = 40
N_DESKS = 4
STRATEGIES_PER_DESK = 2
BOOKS_PER_STRATEGY = 2
TRADES_PER_BOOK = 4
QUANTITY = 10.0
SPOT = 100.0

# 4 × 2 × 2 × 4
EXPECTED_N_POSITIONS = N_DESKS * STRATEGIES_PER_DESK * BOOKS_PER_STRATEGY * TRADES_PER_BOOK
# firm + portfolio + desks + strategies + books + trades
EXPECTED_N_NODES = (
    1
    + 1
    + N_DESKS
    + N_DESKS * STRATEGIES_PER_DESK
    + N_DESKS * STRATEGIES_PER_DESK * BOOKS_PER_STRATEGY
    + EXPECTED_N_POSITIONS
)
EXPECTED_MARKET_VALUE = EXPECTED_N_POSITIONS * QUANTITY * SPOT
# SHA-256 of rounded path/level/MV/delta/VaR/ES/stress lines (host-independent).
EXPECTED_CHECKSUM = "6a9c1124e91805528f550cfe4ae922f19155342cbac3c0d4947bdc95aa82ef75"

_ADDITIVE = ("market_value", "delta", "gamma", "vega", "dv01", "fx_delta")
DESKS = tuple(f"Desk-{i}" for i in range(N_DESKS))
STRATEGIES = tuple(f"Strat-{i}" for i in range(STRATEGIES_PER_DESK))
BOOKS = tuple(f"Book-{i}" for i in range(BOOKS_PER_STRATEGY))


def bench_book() -> tuple[Portfolio, MarketSnapshot]:
    positions: list[EquityPosition] = []
    spots: dict[str, float] = {}
    n = 0
    for desk in DESKS:
        for strategy in STRATEGIES:
            for book in BOOKS:
                for _ in range(TRADES_PER_BOOK):
                    symbol = f"SYM{n:03d}"
                    positions.append(
                        EquityPosition(
                            type="equity",
                            id=f"eq-{n:03d}",
                            symbol=symbol,
                            quantity=QUANTITY,
                            book=book,
                            desk=desk,
                            strategy=strategy,
                        )
                    )
                    spots[symbol] = SPOT
                    n += 1
    portfolio = Portfolio(
        id="nightly-hierarchy",
        name="Nightly Hierarchy Book",
        firm="NightlyFirm",
        desk="Unused-Default",
        strategy="Unused-Default",
        positions=positions,
    )
    market = MarketSnapshot(
        id="nightly-hierarchy-mkt",
        equity_spots=spots,
        rates={"USD": 0.04},
    )
    return portfolio, market


def _count_nodes(node) -> int:
    return 1 + sum(_count_nodes(child) for child in node.children)


def assert_additive_reconciles(node, tol: float = 1e-9) -> None:
    if not node.children:
        return
    for attr in _ADDITIVE:
        parent = getattr(node, attr)
        child_sum = sum(getattr(c, attr) for c in node.children)
        if abs(parent - child_sum) > tol:
            raise AssertionError(
                f"{node.level}:{node.name} {attr} {parent} != children {child_sum}"
            )
    parent_stress = {s.scenario: s.pnl for s in node.stress}
    for scenario, parent_pnl in parent_stress.items():
        child_sum = sum(
            next(s.pnl for s in c.stress if s.scenario == scenario) for c in node.children
        )
        if abs(parent_pnl - child_sum) > tol:
            raise AssertionError(
                f"{node.level}:{node.name} stress[{scenario}] {parent_pnl} != {child_sum}"
            )
    for child in node.children:
        assert_additive_reconciles(child, tol)


def tree_checksum(node) -> str:
    lines: list[str] = []

    def walk(n) -> None:
        stress = "|".join(
            f"{s.scenario}={s.pnl:.8f}" for s in sorted(n.stress, key=lambda r: r.scenario)
        )
        lines.append(
            f"{n.path}|{n.level}|{n.market_value:.8f}|{n.delta:.8f}|"
            f"{n.var_99:.8f}|{n.expected_shortfall_99:.8f}|{stress}"
        )
        for child in n.children:
            walk(child)

    walk(node)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def run_hierarchy_identity() -> dict:
    portfolio, market = bench_book()
    pricing = BuiltinPricingEngine()
    engine = HierarchyEngine(
        HistoricalRiskEngine(
            seed=SEED,
            observations=OBSERVATIONS,
            scenario_backend="python",
        )
    )
    started = time.perf_counter()
    root = engine.build(portfolio, pricing, market=market)
    wall_ms = (time.perf_counter() - started) * 1000.0
    assert_additive_reconciles(root)
    n_nodes = _count_nodes(root)
    checksum = tree_checksum(root)
    if n_nodes != EXPECTED_N_NODES:
        raise AssertionError(f"n_nodes {n_nodes} != {EXPECTED_N_NODES}")
    if len(portfolio.positions) != EXPECTED_N_POSITIONS:
        raise AssertionError(
            f"n_positions {len(portfolio.positions)} != {EXPECTED_N_POSITIONS}"
        )
    if abs(float(root.market_value) - EXPECTED_MARKET_VALUE) > 1e-9:
        raise AssertionError(
            f"market_value {root.market_value} != {EXPECTED_MARKET_VALUE}"
        )
    if abs(float(root.delta) - EXPECTED_MARKET_VALUE) > 1e-9:
        raise AssertionError(f"delta {root.delta} != {EXPECTED_MARKET_VALUE}")
    payload = {
        "impl": IMPL,
        "n_positions": EXPECTED_N_POSITIONS,
        "n_nodes": n_nodes,
        "n_desks": N_DESKS,
        "market_value": float(root.market_value),
        "delta": float(root.delta),
        "var_99": float(root.var_99),
        "expected_shortfall_99": float(root.expected_shortfall_99),
        "checksum": checksum,
        "additive_ok": True,
        "seed": SEED,
        "observations": OBSERVATIONS,
        "scenario_backend": "python",
        "wall_ms": wall_ms,
    }
    if EXPECTED_CHECKSUM != "PENDING_LOCAL_PIN" and checksum != EXPECTED_CHECKSUM:
        raise AssertionError(f"checksum {checksum} != {EXPECTED_CHECKSUM}")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a single JSON object (wall_ms recorded, not SLA-gated).",
    )
    args = parser.parse_args(argv)
    payload = run_hierarchy_identity()
    if args.json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(
            "hierarchy benchmark identity ok",
            payload["checksum"],
            f"n_nodes={payload['n_nodes']}",
            f"market_value={payload['market_value']}",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
