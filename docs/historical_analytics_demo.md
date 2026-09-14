# Historical Analytics Demo Script (Wave B)

One **5–8 minute** walkthrough from packaged synthetic history through SPY-relative analytics, KR-DV01, and the T0/T1 waterfall. All risk numbers come from the backend. This script records **clicks**, **talking points**, and **expected relationships** — it does not invent VaR, beta, drawdown, or DV01 figures.

Related Stage 10.4 golden path: [`demo_script.md`](demo_script.md).

## Demo vs observed data

| Input | What it is | What it is not |
|---|---|---|
| `global-macro` | Packaged **demo** book (`backend/app/sample.py`) | A live production portfolio |
| `data/demo_multi_factor_history.csv` | **Synthetic** per-factor replay (`demo-multi-factor-history` / `v1`) | Observed / licensed vendor history |
| Nested SPY on Historical | Canonical Wave A identity `equity:US:SPY` from the same analytics result | Allocation advice or a live ETF feed |
| `GET /api/v1/market/rates-showcase` | Demo USD OIS/SOFR-style zeros + SensitivityEngine KR-DV01 | Production multi-curve calibration |
| Canned `_DEMO_MARKETS` snapshots | Deterministic local marks | Live market data |
| UI / this script | Displays backend payloads | A source of risk math |

If a number is not on the screen from an API response, do not say it.

## Fresh setup (inline HEAVY)

`POST /api/v1/risk/historical-analytics` is **HEAVY** and is **not** a RiskRun type. Compose `backend` sets `QUANTLINEAGE_EXTERNAL_WORKER=1`, which refuses that POST with HTTP 400 (`details.use=/risk/runs`). Do not quote a VaR from that error.

For this walkthrough, run the API **in-process** so inline HEAVY is allowed (flags unset):

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

No cloud. No live vendors. Local loopback only. Optional idempotent re-seed if you are on Postgres instead of in-memory:

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/seed_golden_demo.py
```

If port 8000 is already Compose, stop that API first. `docker compose up --build` remains the Stage 10.4 golden-demo path; it does not serve this Historical POST until HA is a RiskRun job.

## Hashes and landing cards

| Step | Hash | Card `id` / nav |
|---|---|---|
| Data | `#market-data` | **Market Data** |
| Historical analytics | `#historical-analytics` | **Historical** |
| Contributors | `#var-es/contributors` | `var-es-contributors` |
| KR-DV01 | `#risk-factors/kr-dv01` | `risk-factors-kr-dv01` |
| T0/T1 waterfall | `#var-es/risk-change` | `var-es-risk-change` |
| Provenance | `#risk-runs` | **Risk Runs** → **Calculation provenance** |

`#var-es` alone is the VaR & ES section root (both cards). The two related links on Historical must not share that hash.

## Minute-by-minute flow

### 1. Data (~45s)

- Open `http://127.0.0.1:5173/#market-data` (nav **Market Data**).
- Confirm heading **Global Macro Demo** (catalog id `global-macro`; also `GET /api/v1/portfolios`) once the book name is loaded. Market Data still renders if dashboard is slow.
- Type `SPY` in **Instrument search**, click **Search** (`GET /api/v1/instruments/search`).
- Optionally **Load History** (`GET /api/v1/market/history/{id}`) or **Inspect quality** (`GET /api/v1/instruments/{id}/quality`).
- **Talk:** this is the curated catalog + lineage, not a vendor plant. Default Compose/API history remains packaged synthetic. **Freeze dataset** / **Build snapshot** are optional public-data actions (`POST /api/v1/data/datasets`, `POST /api/v1/market/snapshots/from-public-data`); skip them unless you already froze a public artifact. The browser does not call Yahoo or FRED.

**Expect:** a SPY row with capabilities from the catalog payload. Do not invent coverage dates or a content hash.

### 2. Historical analytics (~60s)

- Nav **Historical**, or `http://127.0.0.1:5173/#historical-analytics`.
- Leave **Start date** `2024-01-02` and **End date** `2024-11-15` (packaged demo coverage). The page POSTs `POST /api/v1/risk/historical-analytics` with `include_benchmark: true`, `frequency: DAILY`.
- Point at **identity**: portfolio id/version, `historical_dataset_id` / version, snapshot, range, methodology, annualization (`cagr` · `sqrt_time` · `periods_per_year` from the result).
- Summary table: cumulative / annualized return / vol / max drawdown / Sharpe. Value cells that look like percents are **display formatting** of API fractions; the **Unit** column is `result.units` (`fraction`, `annualized_fraction`, `fraction_of_peak_negative`).
- Click **?** for in-app help. **Talk:** one backend result; the terminal does not annualize or compute Sharpe.

**Expect:** identity names the packaged synthetic panel (typically `demo-multi-factor-history`). Sharpe `undefined` if the API sent `null` (zero-vol note) — do not say 0. Changing **End date** fires a **new** POST; wait for the identity range to match the picker.

### 3. SPY comparison (~45s)

- Same page, block **SPY benchmark** (`data-testid="ha-benchmark"`).
- Point at `instrument_id` / `factor_column`, then excess return, beta, tracking error, relative drawdown, correlation, aligned window.
- **Talk:** nested `benchmark` on the **same** result. Relative analytics, not a recommendation to buy or hedge SPY. Units come from `benchmark.units` (`dimensionless` beta, `annualized_fraction` tracking error, `fraction` excess).

**Expect:** instrument identity `equity:US:SPY`. If the page is an error alert (missing SPY / overlap / HEAVY refuse), stop — do not invent a beta.

### 4. Drawdown / risk (~45s)

- Still on Historical: **Drawdown** chart (`ha-drawdown-chart`) then **VaR / ES**.
- **Talk:** drawdown series and `max_drawdown` are API values **≤ 0** (`fraction_of_peak_negative`). Charts copy payload `value`s; they do not flip loss to a positive height.
- VaR/ES rows are **currency loss** (`units.var_es`) from `HistoricalRiskEngine` on the sliced window — not a second formula, and not the Overview KPI card.

**Expect:** drawdown caption includes the unit. 95% / 99% VaR and 99% ES show `currency_loss`. ES ≥ VaR on this table is a payload relationship, not a number to memorize.

### 5. Contributors (~45s)

- Click **Component VaR contributors** (hash `#var-es/contributors`) or nav **VaR & ES** and scroll to **Component VaR Contributors**.
- **Talk:** bars and `contribution_pct` are dashboard / `POST /api/v1/risk/contributors` (via `loadDashboard`). Component VaR is an Euler/parametric allocation, **not** an additive split of the Historical page’s quantile VaR.

**Expect:** the card `id` is `var-es-contributors`. This is a different landing target than the waterfall. Shares are API `contribution_pct`.

### 6. KR-DV01 (~45s)

- Click **KR-DV01 tenor curve** (hash `#risk-factors/kr-dv01`) or nav **Risk Factors**.
- Card heading **Rates curve / KR-DV01**. Curve + table from `GET /api/v1/market/rates-showcase` (`key_rate_dv01` by tenor).
- Point at **Parallel DV01 (not KR-DV01)** — field `parallel_dv01`, separately labeled. Unit from `conventions.sensitivity_unit` (currency P&L per +1bp).
- **Talk:** KR buckets are not summed in the browser to invent parallel DV01. Demo OIS/SOFR-style zeros, not a production multi-curve.

**Expect:** KR-DV01 and Parallel DV01 both visible with distinct labels. Do not add the tenor column in your head.

### 7. T0/T1 waterfall (~90s)

- Click **Risk-change waterfall** (hash `#var-es/risk-change`) or stay on **VaR & ES** and scroll to **Risk Change Attribution**.
- Metric `var_99`, methodology `DELTA_GAMMA`, click **Compare T0/T1**.
- Wait until the flagship panel renders (`POST /api/v1/risk/runs/compare`). T1 is the demo SPY×1.5 book vs T0 current book — a **trade** change, same packaged market.
- Waterfall order: **T0 risk** → **portfolio / trade change** → **market / factor changes** → **residual / interactions** → **T1 risk**. Residual is always a column, including `$0`.
- Identity table: portfolio version, snapshot, dataset id/version, methodology, calculation config (T0 vs T1).
- **Talk:** UI only displays the payload. Residual absorbs non-additive VaR; this is not a regulatory P&L-explain certificate. Positive `total_change` follows the payload `sign_convention` (selected **loss-risk** metric increased).

**Expect (relationships, not a quoted VaR):**

- `t0_run_id` ≠ `t1_run_id`; both COMPLETED.
- `total_change` ≠ 0 when SPY scale changes a long equity book.
- `portfolio_trade_change + market_change + residual ≈ total_change` (engine tolerance).
- Trade bucket dominates this demo pair; market bucket near zero when snapshots match.
- Residual label stays on screen. Do not hide it or recompute it as `total_change − trade − market` in the browser.

Skip **Run attribution** (legacy SPY×1.5 `POST /api/v1/risk/change-attribution`) unless you need the secondary path.

### 8. Provenance (~45s)

- On the Compare T0/T1 result, click a T0/T1 run id (`GET /api/v1/risk/runs/{id}`).
- Or click **Calculation provenance** on Historical (`#risk-runs`). **Start run**, then read **Calculation provenance** (`GET /api/v1/risk/runs/{id}/provenance` when present). Do **not** invent a second schema.
- **Talk:** identity is the run: portfolio id/version, snapshot / as_of, historical dataset id/version, pricing engine, methodology, calculation_config.

**Expect:** `historical_dataset_id` names the packaged synthetic panel (typically `demo-multi-factor-history`). `status` is COMPLETED. Missing fields stay empty; do not fill them from memory.

### 9. Honest limitations (~30s)

- Click **?** on Historical analytics, Risk Change Attribution, and Rates curve / KR-DV01.
- Mention [`known_limitations.md`](known_limitations.md): no live vendors; demo history is synthetic; approximations vs full reval; HA is HEAVY inline (not a RiskRun); local loopback is unauthenticated, not a production IAM/cloud deployment.

**Expect:** in-app help says the UI does not compute risk and that demo history is not observed data.

## Timing

Steps 1–4 ~3 min, 5–7 ~3 min, 8–9 ~1–2 min. Skip Freeze dataset / Build snapshot and reverse-stress if the clock is tight.

## What not to say

- Do not claim vendor market data, cloud hosting, or production coverage.
- Do not treat four-macro `demo_historical_factors.csv` as the default demo panel.
- Do not quote frozen dollar VaR, beta, or KR-DV01 from this file or from screenshots as if they were live.
- Do not present residual-zero as a certification that VaR is additive.
- Do not add KR tenor DV01s to “check” Parallel DV01.
- Do not mix Historical-page VaR (sliced window) with Overview 99% VaR without saying they are different API fields.
