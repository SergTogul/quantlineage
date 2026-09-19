# QuantLineage

**Every risk number has a lineage. Every change has an explanation.**

QuantLineage is a portfolio risk terminal that answers one question first: *why did the book’s risk change?* It compares two immutable RiskRuns, splits the move into trades, markets, and residual, and shows the dataset, snapshot, and methodology that produced the figure.

The pricing library prices. QuantLineage manages portfolio risk. The model routes deterministic tools; it never invents VaR, ES, or DV01.

Repo: [github.com/SergTogul/quantlineage](https://github.com/SergTogul/quantlineage)

![Overview — Why did my risk change?](docs/demo/quantlineage_demo_01_overview.png)

## Demo (5–6 minutes)

One path. Local demo book. No live vendors.

1. **Overview** — Global Macro Demo, breaches, KPIs. Click **Why did my risk change?**
2. **Risk-change waterfall** — **Compare T0/T1**. Trades vs markets vs residual, with dataset/snapshot identity.
3. **Historical Analytics** — wealth, drawdown, Sharpe (dimensionless), data-source badge.
4. **Stress / KR-DV01** — named shocks, then the USD rates KR-DV01 tenor curve.
5. **Provenance** — Risk Runs → completed run: portfolio, snapshot, dataset, methodology, release SHA.
6. **AI / MCP** — Risk Query (“Why did my risk change?”) asks for two RiskRun ids and **does not invent VaR**. Optional MCP tools over the same services.

```bash
docker compose up --build
# or local uvicorn + Vite → http://127.0.0.1:5173
```

![Risk-change waterfall](docs/demo/quantlineage_demo_02_risk_change.png)

![Historical Analytics](docs/demo/quantlineage_demo_03_historical.png)

![Risk Query](docs/demo/quantlineage_demo_04_query_provenance.png)

![Calculation provenance](docs/demo/quantlineage_demo_06_provenance.png)

Inputs are packaged: demo books from `GET /api/v1/portfolios`, synthetic panel `data/demo_multi_factor_history.csv`, optional public EOD freeze in [`docs/public_data_demo.md`](docs/public_data_demo.md). Artifact check:

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/check_final_demo.py
```

Longer walkthroughs: [`docs/demo_script.md`](docs/demo_script.md) (institutional UI story) and [`docs/demo/final_demo.md`](docs/demo/final_demo.md) (artifact path).

## What the terminal shows

- Immutable RiskRuns with dataset / snapshot / methodology lineage
- “Why did my risk change?” attribution (trades, markets, residual)
- Historical VaR / ES: Linear, Delta-Gamma, Full Revaluation
- Greeks, DV01, KR-DV01
- Stress and reverse stress
- Firm → Desk → Book → Trade hierarchy
- Typed AI/MCP tools over the same risk services

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

QuantLineage owns aggregation, snapshots, risk, lineage, and workflow. Native C++ accelerates LINEAR/DELTA_GAMMA scenario aggregation only; FULL_REVALUATION stays on `PricingEngine`.

See [`docs/architecture.md`](docs/architecture.md) and [`docs/adr/README.md`](docs/adr/README.md).

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

See [`docs/mcp.md`](docs/mcp.md), [`docs/openai_risk_assistant.md`](docs/openai_risk_assistant.md) (optional server-side OpenAI routing), and [`docs/wave_c_ai_mcp_demo.md`](docs/wave_c_ai_mcp_demo.md).

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
