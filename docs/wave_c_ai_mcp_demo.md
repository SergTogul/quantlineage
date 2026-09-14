# Wave C AI / MCP Demo Script

One **6–8 minute** walkthrough of Risk Query: catalog search → data quality → run risk → contributors → why VaR changed → stress → 10Y KR-DV01 → provenance → unsupported request. All risk numbers come from deterministic tools. This script records **clicks**, **HTTP / chips**, **talking points**, and **relationships** — it does not invent VaR, ES, DV01, quality scores, or run ids.

Related Wave B analytics walkthrough: [`historical_analytics_demo.md`](historical_analytics_demo.md). MCP developer notes: [`mcp.md`](mcp.md).

## Demo vs observed data

| Input | What it is | What it is not |
|---|---|---|
| `global-macro` | Packaged **demo** book (`SAMPLE_PORTFOLIO` / `backend/app/sample.py`) | A live production portfolio |
| Risk Query | Keyword router + allowlisted tools (`POST /api/v1/risk/query`) | A live LLM or a second risk engine |
| `search Apple` | Curated catalog hit `equity:US:AAPL` / Apple Inc. | A vendor plant or trading idea |
| `get_data_quality` | Same `validate_series` path as `GET /api/v1/instruments/{id}/quality` | A second quality engine or invented hash |
| Overview chips | Fill-and-submit prompts on `#overview/command` | Client-side VaR/ES/DV01 |
| MCP stdio | Optional allowlist (`python -m app.mcp`) | Required for this walkthrough |

If a number is not on the screen from `data.card` / `data.provenance` / `data.tool_result`, do not say it.

## Fresh setup (inline HEAVY)

`POST /api/v1/risk/query` is **HEAVY**. Compose `backend` sets `QUANTLINEAGE_EXTERNAL_WORKER=1`, which refuses that POST with HTTP 400 (`details.use=/risk/runs`). Do not quote a VaR from that error.

For this walkthrough, run the API **in-process** so inline HEAVY is allowed (flags unset). Lifespan binds `RiskRunWorker` onto `PortfolioService`, which is what lets **run portfolio risk** / **Run equity-down stress.** enqueue instead of fail-closed.

```bash
# API — 127.0.0.1:8000. Lifespan seeds demo books when DATABASE_URL is unset.
cd backend
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=builtin .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```bash
# UI — 127.0.0.1:5173
cd frontend
npm run dev
```

No cloud. No live LLM. Local loopback only. FastAPI does **not** import MCP (`app.main`). Optional stdio MCP is a separate process (`docs/mcp.md`) and is not this walkthrough.

If port 8000 is already Compose, stop that API first.

## Hashes and landing cards

| Step | Hash | Control |
|---|---|---|
| Risk Query | `#overview/command` | Overview **Command** → **Risk Query** (`golden-demo-risk-query`) |
| Same block | Scenario Builder | **Risk Query** chips also live on that page |
| Risk Runs | `#risk-runs` | Completed run ids / **Calculation provenance** |
| KR-DV01 (optional visual) | `#risk-factors/kr-dv01` | Rates showcase chart; Query still owns the 10Y tool payload |

## Minute-by-minute flow

Copy identities from the JSON the UI already rendered (`data.card`, `data.provenance`, `data.tool_result`). Do not type remembered hashes, VaR, or run ids from this file.

### 1. Search Apple (~30s)

- Open `http://127.0.0.1:5173/#overview/command`.
- Confirm **Risk Query** (`data-testid="golden-demo-risk-query"`). Book heading elsewhere is **Global Macro Demo** (`global-macro`).
- Type `search Apple` in **Risk question**, click **Ask** (`POST /api/v1/risk/query`).
- **Talk:** keyword route → `search_instruments` → `search_catalog`. Not a Yahoo HTTP tool from the browser.

**Expect:** `tool_name=search_instruments`. Hits include catalog identity `equity:US:AAPL`, display name Apple Inc., `source_symbol=AAPL`. Copy `instrument_id` from `data.tool_result.hits[0]`. Do not invent coverage dates.

### 2. Data quality (~45s)

- Type (paste the copied id):

  `show data quality for equity:US:AAPL from 2021-01-04 to 2021-01-08`

  That range is the C7 HTTP execute pin (`test_c7_http_query_service_executes_data_quality`). Quality has no 1826-day cap; a different window is fine if the payload returns. If the tool fails closed (missing series / provider / insufficient observations), **stop** — do not invent `content_hash` or a quality score. Copy `first_observation` / `last_observation` from the payload, not from memory.
- **Talk:** `get_data_quality` is `validate_series` (same as `GET /api/v1/instruments/{id}/quality`). Lineage flags, not a second scoring model. Missing id/range (`show data quality for the book`) clarifies with no digits.

**Expect:** `tool_name=get_data_quality`. Copy `instrument_id`, `source_symbol`, `unit`, `currency`, `frequency`, `adjustment`, `content_hash`, `normalization_version`, `stale` from `data.tool_result`. Card/provenance may only show fields the grounded copier found (often `unit`). No `points` array.

### 3. Run risk (~45s)

- Type `run portfolio risk` (or `run portfolio risk var` if you want `run_type=var`). **Ask**.
- **Talk:** allowlisted `run_portfolio_risk` → `RiskRunWorker.submit`. Status starts `QUEUED`. This is not a number the model made up. Sync `What is 99% VaR?` (`get_var_es`) still dumps a report **without** a RiskRun id — card fields say `not on this payload`. Prefer the enqueue for identity.

**Expect:** `tool_name=run_portfolio_risk`. Copy `id` / `status` / `run_type` / `portfolio_id` from `data.tool_result`. Do not read VaR from this queued payload.

If the answer is the digit-free tool-failure sentence, the API is not the in-process worker (Compose `QUANTLINEAGE_EXTERNAL_WORKER=1` or worker unbound). Fix setup; do not invent VaR.

### 4. Contributors (~30s)

- Click chip **Top contributors?**
- **Talk:** RF-019 `get_contributors` (parametric component VaR, truncated to 5). Not an additive split of Historical-page quantile VaR. Labels and `contribution_pct` are the payload.

**Expect:** `tool_name=get_contributors`. Rank order and percents from `data.tool_result.contributors`. Card metric/value/run id are often `not on this payload` — say that, do not fill them.

### 5. Why VaR changed (~60s)

- Click chip **Why did VaR change?** first.
- **Talk:** two completed RiskRun ids are required. The router does not invent `t0_run_id` / `t1_run_id`.

**Expect (no ids):** clarification, `requires_clarification`, no card, **no digits**.

- Then either:
  - copy two **COMPLETED** ids from `#risk-runs` (Start run, or the Wave B T0/T1 pair), or
  - enqueue a second run and wait until both are COMPLETED,
  - and Ask: `Why did VaR change? {t0_run_id} and {t1_run_id}`.

**Expect (with ids):** `tool_name=explain_risk_change`. Waterfall fields from the stored compare payload: T0/T1 ids, `total_change`, portfolio/trade, market, **stored residual**, contributors, config. Residual is never `total − explained` in the browser. Copy `data.card` / `data.provenance`. Do not quote a VaR from this script.

### 6. Stress (~45s)

- Click chip **Run equity-down stress.**
- **Talk:** allowlisted scenario `eq_down_10` only. Enqueue `run_type=stress`. No arbitrary shock JSON. Optional fallback (sync, no run id): `what is our worst stress scenario?` → `get_worst_stress`; still do not invent the loss.

**Expect:** `tool_name=run_stress` (in-process worker). Copy run `id` / `status` / `request.scenario_id`. Do not quote P&L from memory. If fail-closed, same worker-setup note as step 3.

### 7. 10Y KR-DV01 (~30s)

- Click chip **Show USD 10Y KR-DV01.**
- **Talk:** `get_key_rate_dv01` with `tenor=10Y` from the rates showcase (`GET /api/v1/market/rates-showcase` / `build_rates_showcase`). Unit on rows is `per_bp`. Parallel DV01 is a **separate** field; do not sum tenors. Demo OIS/SOFR-style zeros on the rates-macro book.

**Expect:** `tool_name=get_key_rate_dv01`. Tenor list is `10Y` only. Copy `data.provenance.market_snapshot_id` (demo identity `demo:rates-macro`) and row `unit`. Top-level card `metric`/`value`/`unit` may be `not on this payload` because KR-DV01 lives on `key_rate_dv01[]` — say that. Do not convert `per_bp` to percent.

### 8. Provenance (~45s)

- Type `show provenance for {run_id}` using a **COMPLETED** id from step 3, 6, or `#risk-runs`.
- Without an id, `show run provenance` clarifies (no digits, do not invent lineage).
- **Talk:** `get_run_provenance` copies persisted `GET /api/v1/risk/runs/{id}/provenance`. Same fields as the Risk Runs **Calculation provenance** panel. No secrets. `release_sha` omitted when unknown.

**Expect:** `tool_name=get_run_provenance`. Copy `risk_run_id`, `portfolio_id` / version, `market_snapshot_id`, `as_of`, `historical_dataset_id` / version, `methodology`, `status` from `data.tool_result` / card / provenance. Missing fields stay missing.

### 9. Unsupported request (~20s)

- Type `Should we buy more NVDA tomorrow?` (or `Recommend a personalized trade`).
- **Talk:** advisory / trading is refused. The model cannot invent a hedge or a VaR to size it.

**Expect:** no tool, clarification, **no digits**, no card.

## Timing

Steps 1–4 ~2.5 min, 5–7 ~3 min, 8–9 ~1–2 min. Skip MCP stdio unless someone asks; it is allowlist-only and still not an LLM.

## What not to say

- Do not claim a live LLM, vendor market data as a product feed, or production IAM.
- Do not quote frozen dollar VaR, ES, KR-DV01, or `content_hash` from this file or from screenshots as if they were live.
- Do not treat chip **Why did VaR change?** without two ids as a waterfall.
- Do not add KR tenor DV01s to “check” Parallel DV01.
- Do not mix Overview KPI 99% VaR with Historical-page VaR or with a queued RiskRun.
- Do not present MCP as required for FastAPI.
