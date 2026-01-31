# Demo data (Milestone 10)

## Portfolios (M10.1)

Themed demo books live in-code as `backend/app/sample.py` (`DEMO_PORTFOLIOS` /
`SAMPLE_PORTFOLIO`). Catalog: `GET /api/v1/portfolios`. The former
`data/sample_portfolio.csv` orphan was removed — it was unused and superseded.

## Historical market factors (M10.2)

File: [`demo_historical_factors.csv`](demo_historical_factors.csv)

Synthetic / replay aggregate factor history for Historical VaR and scenario
paths. **No live market-data vendor feeds.**

| Column | Unit |
|--------|------|
| `date` | ISO calendar label (documentation only; engines ignore it) |
| `equity_return` | relative return (`0.01` = +1%) |
| `vol_move` | relative vol-level move |
| `rate_move_bps` | parallel rate move in basis points (`1.0` = +1bp) |
| `fx_return` | relative FX return |

Contents are a frozen replay of `SyntheticHistoricalDataset(seed=7, observations=750)`
so file-backed and seeded-RNG risk paths stay numerically identical.

### How to load

```python
from app.risk.historical_data import (
    load_demo_historical_dataset,
    create_historical_dataset,
)
from app.risk.historical import HistoricalRiskEngine

# Explicit packaged demo
engine = HistoricalRiskEngine(dataset=load_demo_historical_dataset())

# Factory / env (API DI uses this)
# RISKFORGE_HISTORICAL_DATASET=demo|synthetic|/path/to.csv
dataset = create_historical_dataset()           # default: demo CSV
dataset = create_historical_dataset("synthetic")
dataset = create_historical_dataset("/path/to/factors.csv")
```

Risk HTTP routers (`backend/app/api/deps.py`) construct
`HistoricalRiskEngine(dataset=create_historical_dataset())`, so the API default
is the packaged demo CSV (`RISKFORGE_HISTORICAL_DATASET` overrides).
