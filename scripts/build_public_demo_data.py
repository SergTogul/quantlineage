#!/usr/bin/env python3
"""Optional public Wave A freeze/snapshot CLI (repo root).

Usage::

    PYTHONPATH=backend backend/.venv/bin/python scripts/build_public_demo_data.py
    PYTHONPATH=backend backend/.venv/bin/python scripts/build_public_demo_data.py --live

Default does not fetch Yahoo/FRED. Tests inject fakes. ``--live`` is opt-in.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.market.history.public_demo import main, parse_args  # noqa: E402


def live_providers():
    """Yahoo + FRED adapters. Only constructed when ``--live`` is passed."""
    from app.market.ingestion.fred import FredAdapter
    from app.market.ingestion.yahoo import YahooFinanceAdapter

    return YahooFinanceAdapter(), FredAdapter()


def cli(argv: list[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    parsed = parse_args(args_list)
    if parsed.live:
        history, macro = live_providers()
        return main(args_list, history_provider=history, macro_provider=macro)
    return main(args_list)


if __name__ == "__main__":
    raise SystemExit(cli())
