#!/usr/bin/env python3
"""CLI entrypoint for M10.3 deterministic demo risk artifacts.

Usage (from repo root)::

    cd backend && PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=builtin \\
      ../.venv/bin/python ../scripts/run_demo_risk.py --check -o ../data/demo_risk_artifact.json

Or with the backend venv::

    cd backend && PYTHONPATH=. .venv/bin/python -m app.demo.run_demo_risk --check
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.demo.run_demo_risk import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
