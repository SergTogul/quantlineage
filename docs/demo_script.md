# Golden Institutional Demo Script (Stage 10.4)

Canonical **5–6 minute** interview path (README): Overview → Why did my risk change? → Historical Analytics → Stress / KR-DV01 → Provenance → AI/MCP.

This file is the longer institutional UI story from a fresh checkout. All risk numbers come from the backend. It records **clicks**, **talking points**, and **expected relationships** — it does not invent VaR, ES, or P&L figures.

## Demo vs observed data

| Input | What it is | What it is not |
|---|---|---|
| `global-macro` / `equity-vol` / `rates-macro` | Packaged **demo** books (`backend/app/sample.py`) | A live production portfolio |
| `data/demo_multi_factor_history.csv` | **Synthetic** per-factor replay (`demo-multi-factor-history` / `v1`) | Observed / licensed vendor history |
| `data/demo_historical_factors.csv` | Labeled **four-macro fixture** for goldens | The production demo default |
| Canned `_DEMO_MARKETS` snapshots | Deterministic local marks | Live market data |
| UI / this script | Displays backend payloads | A source of risk math |

If a number is not on the screen from an API response, do not say it.

## Fresh setup (no hidden steps)

```bash
docker compose up --build
```

API `127.0.0.1:8000`, UI `127.0.0.1:5173`. Compose lifespan already seeds demo books. Optional idempotent re-seed (safe to run twice; does not duplicate rows):

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/seed_golden_demo.py
```

No cloud. No live vendors. Local loopback only.

## Minute-by-minute flow

### 1. Open the deterministic book (~30s)

- Open `http://127.0.0.1:5173` (default Overview is the **status** blotter, not alternate layouts).
- Confirm heading **Global Macro Demo** (catalog id `global-macro`; also `GET /api/v1/portfolios`).
- **Talk:** this is the cross-asset demo book, not a production desk.

**Expect:** Overview KPIs (Market Value, 99% VaR, 99% ES) show currency amounts from `POST /api/v1/risk/dashboard`. Do not quote a memorized dollar VaR.

### 2. View VaR / ES / Greeks (~45s)

- Stay on **Overview**, then **VaR & ES**.
- Point at 99% VaR and 99% ES on the VaR card; Greeks (Δ, ν, DV01) on **Portfolio → Hierarchy**.
- Click **?** on VaR / ES for methodology copy.
- **Talk:** default demo methodology is `DELTA_GAMMA` (approximation). Historical VaR uses the packaged **synthetic** panel, not observed data. `LINEAR` / `DELTA_GAMMA` are not full revaluation; `FULL_REVALUATION` is a third method, not an SLA.

**Expect:** ES ≥ VaR on the same methodology row (same tail, same engine). Hierarchy DV01 / delta / vega are API node fields, not browser math.

### 3. Hierarchy + contributors (~45s)

- **Portfolio**: drill Firm → desk → book → trade. Child NAV / VaR come from `HierarchyEngine`.
- **VaR & ES → Component VaR Contributors**: ranked trades.
- **Talk:** component VaR is an Euler/parametric allocation, not an additive split of historical quantile VaR.

**Expect:** contributor rows exist; shares are API `contribution_pct`. Hierarchy root VaR is the same engine result as the summary, not a second formula in the UI.

### 4. Stress (~45s)

- **Stress → Stress Tests**.
- **Talk:** named shocks revalue the book vs the base snapshot. Signs are P&L (negative = loss). Crisis names are library labels, not claimed historical replay unless the row says so.

**Expect:** at least one row; equity-down scenarios should not print as gains on a long-equity book. Do not recite artifact dollar P&Ls from memory.

### 5–7. Compare two RiskRuns / “Why did my risk change?” / attribution (~2 min)

- **Scenario Builder → Risk Query**: ask `Why did my risk change?`
- **Expect:** clarification asking for two completed RiskRun ids. The model/router must **not** invent a VaR.
- **VaR & ES → Risk Change Attribution**: metric `var_99`, methodology `DELTA_GAMMA`, click **Compare T0/T1**.
- Wait until the flagship panel renders (POST `/api/v1/risk/runs/compare`). T1 is the demo SPY×1.5 book vs T0 current book — a **trade** change, same packaged market.
- **Talk:** flagship explain is two immutable RiskRuns. UI only displays the payload. Residual absorbs non-additive VaR; this is not a regulatory P&L-explain certificate.

**Expect (relationships, not a quoted VaR):**

- `t0_run_id` ≠ `t1_run_id`; both COMPLETED.
- `total_change` ≠ 0 when SPY scale changes a long equity book.
- `portfolio_trade_change + market_change + residual ≈ total_change` (engine tolerance).
- Trade bucket dominates this demo pair; market bucket near zero when snapshots match.
- Factor / hierarchy tables are backend contributor lists. Positive `total_change` means the selected **loss-risk** metric increased.

### 8–10. Hedge, recalculate, show reduced risk (~1.5 min)

- **Scenario Builder → Hedge Compare**, methodology `DELTA_GAMMA`, **Compare hedge**.
- **Talk:** demo hedge flats SPY equity quantity. The card **recalculates** base vs hedged through `POST /api/v1/risk/stress/formal/compare`.

**Expect:** `base_var_99 ≠ hedged_var_99` and `var_improvement ≠ 0` from that JSON. Direction: flattening a long SPY sleeve should not increase 99% VaR on this demo book. UI Δ is the API `var_improvement`, not a client subtract.

### 11. Provenance (~45s)

- On the Compare T0/T1 result, click a T0/T1 run id (GET `/api/v1/risk/runs/{id}`).
- **Risk Runs**: **Start run**, then open **Calculation provenance** (Stage 10.5 GET `/api/v1/risk/runs/{id}/provenance` when present). Do **not** invent a second schema.
- **Talk:** identity is the run: portfolio id/version, snapshot / as_of, historical dataset id/version, pricing engine, methodology, calculation_config.

**Expect:** `historical_dataset_id` names the packaged synthetic panel (typically `demo-multi-factor-history`). `status` is COMPLETED. Missing fields stay empty; do not fill them from memory.

### 12. Honest methodology / limitations (~45s)

- Click **?** on Risk Change Attribution (and optionally VaR / ES, Risk Runs).
- Mention [`docs/known_limitations.md`](known_limitations.md): no live vendors; demo history is synthetic; approximations vs full reval; no FULL_REVALUATION HTTP SLA; local Compose is unauthenticated loopback, not a production IAM/cloud deployment.

**Expect:** in-app help says the UI does not compute risk and that demo history is not observed data.

## Timing

Steps 1–4 ~3 min, 5–7 ~2 min, 8–12 ~2–3 min. Skip reverse-stress search if the clock is tight; it is not required for this story.

## What not to say

- Do not claim vendor market data, cloud hosting, or production coverage.
- Do not treat four-macro `demo_historical_factors.csv` as the default demo panel.
- Do not quote frozen dollar VaR from this file or from screenshots as if they were live.
- Do not present residual-zero as a certification that VaR is additive.
