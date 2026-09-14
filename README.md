# QuantLineage

**AI-Powered Multi-Asset Risk & Attribution Platform**

QuantLineage is an institutional-style portfolio risk platform that calculates risk deterministically, preserves the lineage of every calculation, and explains why risk changed across markets, trades, and factors.

> The pricing library prices. QuantLineage manages portfolio risk.
> The model orchestrates deterministic tools; it never calculates financial risk itself.

## Why QuantLineage

- Multi-asset pricing through a clean `PricingEngine` boundary
- Historical VaR / ES: Linear, Delta-Gamma, Full Revaluation
- Greeks, DV01 and KR-DV01
- Stress and reverse stress
- Firm → Desk → Book → Trade risk hierarchy
- “Why did my risk change?” attribution
- Immutable RiskRuns with dataset/snapshot/methodology lineage
- Public EOD equity/rates ingestion + deterministic offline demo
- Typed AI/MCP tools over deterministic risk services

## Signature Workflow — Why Did My Risk Change?

Open the terminal on the default **status** Overview. The hero action **Why did my risk change?** jumps to the Risk Change Attribution waterfall (`#var-es/risk-change`).

That panel compares two completed RiskRuns (T0 → T1) and attributes the change to trades, markets, and residual. Drivers, residual, and identity come from `POST /api/v1/risk/runs/compare`. The UI never recomputes VaR.

Talk track: the book moved; here is whether it was the inventory, the market, or leftover interaction — with the dataset and snapshot that produced the numbers.

## Architecture

```text
Portfolio / Position
  -> PricingEngine (QuantLib adapter or builtin)
  -> MarketSnapshot + MarketDataProvider
  -> Risk engines (VaR/ES, stress, reverse stress, hierarchy, limits, attribution)
  -> PortfolioService
  -> FastAPI `/api/v1`
  -> React risk terminal (display only)
  -> Optional MCP/tool router over the same deterministic services
```

The pricing library prices. QuantLineage owns aggregation, snapshots, risk, lineage, and workflow. Native C++ accelerates LINEAR/DELTA_GAMMA scenario aggregation only; FULL_REVALUATION stays on `PricingEngine`.

See [`docs/architecture.md`](docs/architecture.md) and [`docs/adr/README.md`](docs/adr/README.md).

## Demo

Five to eight minutes from a clean checkout:

1. `docker compose up --build` (or local uvicorn + Vite). Open `http://127.0.0.1:5173` — default Overview is the **status** blotter.
2. Confirm **QUANTLINEAGE** in the nav and **Global Macro Demo** as the book heading.
3. Click **Why did my risk change?** → Risk Change Attribution. Run **Compare T0/T1**.
4. Historical Analytics: wealth, drawdown, Sharpe (dimensionless), data-source badge.
5. Scenario Builder, Risk Query (“Why did my risk change?”), then Risk Runs provenance.

Inputs are local: demo books from `GET /api/v1/portfolios`, packaged synthetic history at `data/demo_historical_factors.csv` / `data/demo_multi_factor_history.csv`, optional public EOD freeze in [`docs/public_data_demo.md`](docs/public_data_demo.md). Artifact: `data/demo_risk_artifact.json`.

Walkthroughs: [`docs/demo/final_demo.md`](docs/demo/final_demo.md) (3–5 min artifact path) and [`docs/demo_script.md`](docs/demo_script.md) (institutional UI story).

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/check_final_demo.py
```

![Overview](docs/demo/quantlineage_demo_01_overview.png)

## Quant Methodology

Three Historical VaR/ES modes:

- `LINEAR` — first-order Greek approximation
- `DELTA_GAMMA` — delta-gamma plus vega, DV01, and FX delta (demo default)
- `FULL_REVALUATION` — reprice historical shocked snapshots through `PricingEngine`

Stress and reverse stress are deterministic. Multi-factor reverse stress is a constrained adverse-orthant ray search plus coordinate descent — not a certified global optimizer.

Coverage is scoped: equities, equity futures, European equity options, bonds, vanilla IRS, FX forwards, European FX options, IR futures, vanilla caps/floors and European swaptions.

See [`docs/methodology/README.md`](docs/methodology/README.md), [`docs/methodology/multi_factor_reverse_stress.md`](docs/methodology/multi_factor_reverse_stress.md), and [`docs/known_limitations.md`](docs/known_limitations.md).

## AI / MCP

Typed tools over the same risk services. The model routes; it does not invent VaR, ES, or DV01.

```json
{
  "mcpServers": {
    "quantlineage": {
      "command": "python",
      "args": ["-m", "app.mcp"],
      "cwd": "backend",
      "env": { "PYTHONPATH": ".", "QUANTLINEAGE_MCP_AUTHORIZATION": "Bearer <token-if-shared>" }
    }
  }
}
```

See [`docs/mcp.md`](docs/mcp.md) and [`docs/wave_c_ai_mcp_demo.md`](docs/wave_c_ai_mcp_demo.md).

## Run Locally

Requires **Python 3.12+** (`numpy>=2.3`). On macOS 13 where Homebrew Python 3.12 may not build, install via [uv](https://github.com/astral-sh/uv).

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
QUANTLINEAGE_PRICING_ENGINE=quantlib uvicorn app.main:app --reload
```

Builtin engine (no QuantLib):

```bash
QUANTLINEAGE_PRICING_ENGINE=builtin uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend && npm install && npm run dev
```

**Compose** (Postgres `quantlineage` / volume `quantlineage_pgdata`, API, worker, frontend):

```bash
docker compose up --build
```

DSN: `postgresql+psycopg://quantlineage:quantlineage@localhost:5432/quantlineage`. Compose backend sets `QUANTLINEAGE_EXTERNAL_WORKER=1`; the worker claims queued RiskRuns. Shared/non-loopback requires `QUANTLINEAGE_SHARED_DEPLOYMENT=1` and `QUANTLINEAGE_API_TOKEN`. See Persistence notes in [`BUILD_NOTES.md`](BUILD_NOTES.md).

Canonical API prefix is `/api/v1`. OpenAPI title is **QuantLineage API**. Legacy unversioned paths remain dual-mounted until the published sunset.

## Tests / CI

```bash
cd backend
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=builtin pytest -q
ruff check app tests
mypy app

cd ../frontend
npm test && npm run lint && npm run build

cd ../e2e
npm install && npm run install:browsers && npm test
```

CI jobs: backend pytest, QuantLib hard-gate, PR-FAST, frontend test/build, lint, Playwright E2E, Postgres smoke, PR-FULL. Native kernel tests compile C++20 when `g++` is present.

Optional native kernel and SLA evidence: [`docs/performance.md`](docs/performance.md), [`benchmarks/README.md`](benchmarks/README.md).

## Known Limitations

- No live market-data vendor integration; default history is packaged synthetic replay.
- Typed historical factors are EquitySpot, EquityVol, RateZero, FXSpot, FXVol; IR vol and dividend/funding maps are not a full factor taxonomy.
- Curves and vol surfaces are scoped demo inputs, not production calibration.
- Caps/floors/swaptions are vanilla Black-76; no Bermudan/vol cube.
- Multi-factor reverse stress is constrained, not a certified global optimum.
- AI is a deterministic tool-routing slice; no hosted LLM is claimed.
- Redis/RQ is deferred; durable claim safety uses Postgres `SKIP LOCKED`.

Fuller catalog: [`docs/known_limitations.md`](docs/known_limitations.md).
