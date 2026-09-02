# RiskForge

Institutional-style multi-asset portfolio and derivatives risk management MVP. Pricing is an adapter; portfolio risk, stress, limits, attribution, hierarchy and UI are application-owned.

## Architecture

- **PricingEngine interface**: QuantLib adapter (default in production) + deterministic built-in reference adapter.
- **MarketDataProvider**: immutable `MarketSnapshot` objects for equities, vols, FX and rates.
- **Risk layer**: historical/parametric VaR, Expected Shortfall, component VaR, risk factors, stress/reverse stress, limits, hierarchy and attribution.
- **Compute kernel**: Python reference kernel plus optional C++20/`ctypes` scenario kernel.
- **API**: FastAPI.
- **UI**: React/Vite risk terminal with scenario builder, reverse stress and deterministic risk query.

## Instruments

- Equities
- Equity futures
- European equity options
- Bonds
- Vanilla interest-rate swaps
- FX forwards
- European FX options

QuantLib currently handles the original equity option/bond/swap path. New product types use the reference adapter until native QuantLib implementations are added; this is isolated behind `PricingEngine`.

## Risk capabilities

- Delta, gamma, vega, DV01 and FX delta
- Risk-factor/bucket aggregation
- Historical-style VaR / Expected Shortfall
- Parametric VaR / Expected Shortfall
- Component VaR by position
- Stress and threat scenario evaluation
- Instrument-specific and multi-factor shocks
- Custom scenario builder
- Reverse stress solving
- Before/after hedge scenario comparison
- Risk limits and breaches
- Portfolio → desk → strategy → book → trade hierarchy
- P&L attribution across position, equity, vol, rate and FX changes
- Deterministic natural-language query router ready to sit behind an LLM tool layer

## Main API endpoints

```text
GET  /health
GET  /portfolio
POST /market/snapshot
POST /risk/summary
POST /risk/factors
POST /risk/var
POST /risk/hierarchy
POST /risk/attribution
POST /risk/attribution/demo
POST /risk/contributors
POST /risk/limits
POST /risk/stress
GET  /risk/stress/scenarios
POST /risk/stress/evaluate
POST /risk/stress/evaluate/custom
POST /risk/stress/reverse
POST /risk/stress/compare
POST /risk/query
```

## Run backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
RISKFORGE_PRICING_ENGINE=quantlib uvicorn app.main:app --reload
```

For development/testing without QuantLib:

```bash
RISKFORGE_PRICING_ENGINE=builtin uvicorn app.main:app --reload
```

## Run frontend

```bash
cd frontend
npm install
npm run dev
```

## Tests

```bash
cd backend
PYTHONPATH=. RISKFORGE_PRICING_ENGINE=builtin pytest -q

cd ../frontend
npm test
```

The backend native-kernel tests compile and execute C++20 with `g++` when a compiler is available. QuantLib runtime tests skip only when the QuantLib wheel is absent.

## Optional native scenario kernel

```bash
cd backend/native
g++ -std=c++20 -O3 -shared -fPIC src/risk_kernel_capi.cpp -o libriskkernel.so
```

Load it with `app.compute.kernel.NativeScenarioKernel`. No pybind11 is required for this MVP seam.

## Design rule

**The pricing library prices; RiskForge manages portfolio risk.** QuantLib/OpenGamma-style analytics can be replaced or extended without rewriting the portfolio-risk workflows.

## Code intelligence (CodeGraph)

This repo can be indexed locally with [CodeGraph](https://github.com/colbymchenry/codegraph) so Cursor and other agents can query symbols, call paths, and blast radius via MCP.

```bash
# Install CLI (once): npm i -g @colbymchenry/codegraph
codegraph init    # creates .codegraph/ (local index, gitignored)
codegraph status  # index stats
codegraph query VaR
```

The SQLite index under `.codegraph/` is machine-local; re-run `codegraph init` or rely on auto-sync after cloning.
