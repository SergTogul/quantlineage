#!/usr/bin/env python3
"""CLI for Stage 10.4 idempotent golden-demo seed.

Usage (from repo root, backend venv)::

    PYTHONPATH=backend backend/.venv/bin/python scripts/seed_golden_demo.py

Or inside the backend package::

    cd backend && PYTHONPATH=. .venv/bin/python -m app.demo.seed

Safe to re-run. Does not replace Compose / API lifespan seed; it reuses that
path. Demo books are packaged sample data, not observed markets.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.demo.seed import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
