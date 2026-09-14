# Demo data (Workstream 10)

## Portfolios Themed demo books live in-code as `backend/app/sample.py` (`DEMO_PORTFOLIOS` /
`SAMPLE_PORTFOLIO`). Catalog: `GET /api/v1/portfolios`. The former
`data/sample_portfolio.csv` orphan was removed — it was unused and superseded.

## Per-factor historical panel (production demo default)

File: [`demo_multi_factor_history.csv`](demo_multi_factor_history.csv)

Synthetic / replay **per-factor** history for Historical VaR. Independent
`SeedSequence` streams (same family distributions as
`create_synthetic_factor_panel`). Dates are the packaged file calendar (same
dates as the four-macro fixture). **No live market-data vendor feeds. Not
observed market data.**

Identity: `demo-multi-factor-history` / `v1`. Projection: `per_factor`.
`is_per_name_per_tenor_panel` is true. Columns map 1:1 onto typed `RiskFactor`s
(no family-wide broadcast).

Shock units:

| Column | Unit |
|--------|------|
| `date` | ISO calendar from the file (used as the panel calendar) |
| `EquitySpot:*` / `FXSpot:*` | relative return (`0.01` = +1%) |
| `EquityVol:*` / `FXVol:*` | relative vol-level change |
| `RateZero:USD:*` | basis points (`1.0` = +1bp) |

## Four-macro fixture (labeled, not the production default)

File: [`demo_historical_factors.csv`](demo_historical_factors.csv)

Labeled `projection="four_macro_demo"` fixture for goldens and
`HistoricalRiskEngine(factor_panel=None)`. Four aggregate columns; when a
panel is built from this file it may still broadcast each family column onto
typed factors of that family.

| Column | Unit |
|--------|------|
| `date` | ISO calendar label |
| `equity_return` | relative return (`0.01` = +1%) |
| `vol_move` | relative vol-level move |
| `rate_move_bps` | parallel rate move in basis points (`1.0` = +1bp) |
| `fx_return` | relative FX return |

Contents are a frozen replay of `SyntheticHistoricalDataset(seed=7, observations=750)`
so file-backed four-macro and seeded-RNG four-macro paths stay numerically identical.

### How to load

```python
from app.risk.historical_data import (
    load_demo_multi_factor_dataset,
    load_demo_historical_dataset,
    create_historical_dataset,
)
from app.services.risk_factories import build_historical_risk_engine

# Production factory default: per-factor panel
engine = build_historical_risk_engine()

# Explicit packaged per-factor file
dataset = load_demo_multi_factor_dataset()

# Labeled four-macro fixture
dataset = load_demo_historical_dataset()
dataset = create_historical_dataset("demo")

# Factory / env
# QUANTLINEAGE_HISTORICAL_DATASET=demo-multi-factor-history|demo|synthetic|/path/to.csv
dataset = create_historical_dataset()  # default: per-factor demo CSV
```

Risk HTTP routers construct the stack via `build_portfolio_service()`, so the
API default is the per-factor demo panel (`QUANTLINEAGE_HISTORICAL_DATASET` overrides).

## Deterministic demo scripts CLI / module: `backend/app/demo/run_demo_risk.py` (shim: `scripts/run_demo_risk.py`).

Loads all demo portfolios + the production historical panel, runs summary VaR and
`DEFAULT_SCENARIOS` stress through `PortfolioService`, and writes sorted-key
JSON. Default pricing for artifacts is **builtin** (set
`QUANTLINEAGE_PRICING_ENGINE`); scenario kernel forced to Python for parity.

Frozen reference artifact: [`demo_risk_artifact.json`](demo_risk_artifact.json)

```bash
cd backend
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=builtin QUANTLINEAGE_PRICING_CACHE=0 \
 .venv/bin/python -m app.demo.run_demo_risk --check -o ../data/demo_risk_artifact.json
```

`--check` fails if two consecutive builds are not byte-identical. Evidence:
`backend/tests/test_demo_scripts.py`. QA-024 compares QuantLib demo numbers to
this artifact on a relative range, not byte-equality.
