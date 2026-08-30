"""Idempotent golden-demo seed (Stage 10.4).

Reuses persistence wiring so Compose / API lifespan seed remains the source of
truth. A second run does not duplicate portfolios, snapshots, scenarios, or
limits. Demo catalog books are packaged sample data, not observed markets.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyLimitDefinitionRepository,
    SqlAlchemyMarketSnapshotRepository,
    SqlAlchemyPortfolioRepository,
    SqlAlchemyScenarioDefinitionRepository,
)
from app.persistence.wiring import (
    DEFAULT_MARKET_SNAPSHOT_ID,
    PersistenceWiring,
    build_persistence_wiring,
)
from app.risk.historical_data import DEMO_MULTI_FACTOR_DATASET_ID
from app.sample import DEMO_PORTFOLIOS, SAMPLE_PORTFOLIO

GOLDEN_DEMO_PORTFOLIO_ID = SAMPLE_PORTFOLIO.id
GOLDEN_DEMO_DATA_CLASS = "demo"


def _sql_inventory(wiring: PersistenceWiring) -> dict[str, Any]:
    if wiring.session_factory is None:
        return {
            "portfolio_ids": [],
            "scenario_count": 0,
            "limit_count": 0,
            "market_snapshot_present": False,
        }
    with session_scope(wiring.session_factory) as session:
        portfolio_ids = list(SqlAlchemyPortfolioRepository(session).list_ids())
        scenario_count = len(SqlAlchemyScenarioDefinitionRepository(session).list_all())
        limit_count = len(SqlAlchemyLimitDefinitionRepository(session).list_for_portfolio(None))
        market = SqlAlchemyMarketSnapshotRepository(session).get(DEFAULT_MARKET_SNAPSHOT_ID)
    return {
        "portfolio_ids": portfolio_ids,
        "scenario_count": scenario_count,
        "limit_count": limit_count,
        "market_snapshot_present": market is not None,
    }


def _delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, int]:
    demo_ids = {p.id for p in DEMO_PORTFOLIOS}
    before_ids = set(before["portfolio_ids"])
    after_ids = set(after["portfolio_ids"])
    return {
        "portfolios": len((after_ids - before_ids) & demo_ids),
        "scenarios": max(0, int(after["scenario_count"]) - int(before["scenario_count"])),
        "limits": max(0, int(after["limit_count"]) - int(before["limit_count"])),
        "market_snapshot": 0 if before["market_snapshot_present"] else int(after["market_snapshot_present"]),
    }


def _already_present(before: dict[str, Any]) -> dict[str, int]:
    demo_ids = {p.id for p in DEMO_PORTFOLIOS}
    return {
        "portfolios": len(set(before["portfolio_ids"]) & demo_ids),
        "scenarios": int(before["scenario_count"]),
        "limits": int(before["limit_count"]),
        "market_snapshot": int(before["market_snapshot_present"]),
    }


def seed_golden_demo(*, url: str | None = None) -> dict[str, Any]:
    """Seed demo catalog + snapshot/scenarios/limits. Safe to re-run.

    Parameters
    ----------
    url:
        Optional SQLAlchemy URL. ``None`` uses ``RISKFORGE_DATABASE_URL`` when
        set; otherwise in-memory wiring (in-code ``DEMO_PORTFOLIOS``).
    """
    catalog_ids = [p.id for p in DEMO_PORTFOLIOS]
    empty = build_persistence_wiring(url=url, seed_sample=False, ensure_schema=True)
    if not empty.enabled:
        return {
            "status": "ok",
            "mode": "memory",
            "data_class": GOLDEN_DEMO_DATA_CLASS,
            "default_portfolio_id": GOLDEN_DEMO_PORTFOLIO_ID,
            "historical_dataset_id": DEMO_MULTI_FACTOR_DATASET_ID,
            "portfolio_ids": catalog_ids,
            "scenario_count": 0,
            "limit_count": 0,
            "inserted": {"portfolios": 0, "scenarios": 0, "limits": 0, "market_snapshot": 0},
            "already_present": {
                "portfolios": len(catalog_ids),
                "scenarios": 0,
                "limits": 0,
                "market_snapshot": 0,
            },
            "session_factory": None,
        }

    before = _sql_inventory(empty)
    wiring = build_persistence_wiring(url=url, seed_sample=True, ensure_schema=True)
    after = _sql_inventory(wiring)
    return {
        "status": "ok",
        "mode": "sqlalchemy",
        "data_class": GOLDEN_DEMO_DATA_CLASS,
        "default_portfolio_id": GOLDEN_DEMO_PORTFOLIO_ID,
        "historical_dataset_id": DEMO_MULTI_FACTOR_DATASET_ID,
        "portfolio_ids": [pid for pid in catalog_ids if pid in set(after["portfolio_ids"])],
        "scenario_count": after["scenario_count"],
        "limit_count": after["limit_count"],
        "inserted": _delta(before, after),
        "already_present": _already_present(before),
        "session_factory": wiring.session_factory,
    }


def _report_for_cli(report: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in report.items() if k != "session_factory"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 10.4: idempotent golden-demo seed (demo books + packaged "
            "synthetic history; no live vendors)."
        )
    )
    parser.add_argument(
        "--url",
        default=None,
        help="SQLAlchemy URL (default: RISKFORGE_DATABASE_URL or in-memory catalog).",
    )
    args = parser.parse_args(argv)
    report = seed_golden_demo(url=args.url)
    sys.stdout.write(json.dumps(_report_for_cli(report), sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
