# Wave A — A0 Integration Map

Inspected on branch `feat/quantlineage-wave-a` at `974798e`. This is the reuse map for G1–G8. Do not invent a second market domain or a second VaR engine.

## Current abstractions to reuse

| Concern | Reuse | Notes |
|---|---|---|
| Immutable marks | `MarketSnapshot` (`backend/app/domain/models.py`) | Frozen nested maps; `content_hash()` hashes marks excluding id/as_of. Snapshot rates are **decimal levels**. |
| Snapshot resolver | `MarketDataProvider` / `FixedMarketDataProvider` (`backend/app/market/snapshot.py`) | Portfolio→snapshot binding for RiskRun. **Not** a public HTTP provider. Do not overload this ABC for Yahoo/FRED. |
| Demo marks | `demo_market_snapshot` (`backend/app/sample.py`) | Canned demo books only. Public-data snapshots must be built separately, then persisted and bound by id. |
| Historical source protocol | `HistoricalMarketDataset` (`backend/app/risk/historical_data.py`) | `factor_observations()` + `projection`. Production demo is `PerFactorFileHistoricalDataset` (`demo-multi-factor-history` / `v1`). |
| Dataset factory | `create_historical_dataset` + `resolve_dataset_source` / `build_historical_risk_engine` (`historical_data.py`, `risk_factories.py`) | Env `RISKFORGE_HISTORICAL_DATASET`. Known ids: demo-multi-factor, demo four-macro, synthetic, `file:<csv>`. Wave A adds frozen public dataset ids here — never HTTP. |
| Factor panel | `HistoricalFactorPanel` + `factor_panel_from_dataset` | Per-name / per-tenor. Projection must not be `four_macro_demo`. |
| Units | `app.risk.shock_units` | Equity/FX = relative return; historical rates = bp; snapshot rates = decimal. Reuse `bps_to_decimal_rate` / `decimal_rate_to_bps`. |
| Risk engine | `HistoricalRiskEngine` | Consumes dataset + optional panel + explicit `MarketSnapshot`. Never call providers. |
| RiskRun identity | `RiskRun.historical_dataset_id/version`, `market_snapshot_id`, `as_of`, `calculation_config` | Already first-class + provenance (`GET /risk/runs/{id}/provenance`). |
| Persistence | `MarketSnapshotRepository.save/get/get_meta` | Snapshot `meta` JSON can carry public-data lineage without a second snapshot table. Dataset freeze can be file/CSV + metadata first (G4). |
| API errors | `app.api.errors.ErrorBody` `{code,message,details}` | Map provider taxonomy onto existing codes (`not_found`, `rate_limited`, `service_unavailable`, …). |
| HTTP client | `httpx` already in `backend/requirements.txt` | Use only inside ingestion adapters. |
| Frontend | `frontend/src/api.js` talks to `/api/v1` only | Provenance UI already exists. G6 adds a Data/Market Data section; do not call providers from the browser. |
| CI | `.github/workflows/ci.yml` | `pytest -q` with no live-network expectation. Wave A tests must be fixture-backed. |

## Dependency direction (must stay)

```text
adapters (httpx) → normalized models
                → validate / quality
                → freeze HistoricalDataset / MarketSnapshot
                → HistoricalFactorPanel
                → HistoricalRiskEngine / RiskRun

app.risk.* and app.pricing.* MUST NOT import adapter modules.
Browser MUST NOT call providers.
```

## Files likely to change

### G1 (ingestion only)
- **New:** `backend/app/market/ingestion/` (models, protocols, errors, yahoo, fred)
- **New:** `backend/tests/test_ingestion_*.py`
- **New:** `docs/data_sources.md`
- **Do not edit:** `historical.py`, `factor_panel.py`, `domain/models.py` MarketSnapshot/RiskRun, pricing, frontend

### G2 (catalog/search)
- New catalog models/service under `app.market.ingestion` or `app.market.catalog`
- `backend/app/main.py` + new API router
- Frontend search UI + `api.js`

### G3 (quality/lineage)
- Quality models can live next to ingestion models (A1.2 already sketches `DataQualitySummary`)
- Later API/UI exposure (A3.5) — keep models now, UI at G3/G6

### G4 (frozen public history)
- `create_historical_dataset` / `resolve_dataset_source` — add `real:<provider>:<name>` ids that load **frozen files**, never HTTP
- Materialization service + scripts
- RiskRun already has dataset id/version columns — bind them

### G5 (public snapshot)
- Builder → `MarketSnapshot` → `MarketSnapshotRepository.save` then `RiskRun.market_snapshot_id`
- Reuse `key_rates[USD][2Y/5Y/10Y]` and decimal `rates`

### G6–G7
- Extend `backend/app/api/market.py` or add `api/instruments.py` / `api/data.py`
- Frontend nav (`frontend/src/lib/nav.mjs`) — **collision risk:** working tree has uncommitted Overview/theme edits on this branch. Wave A UI must not revert or restyle those files except to add a nav section/route.
- `QUANTLINEAGE_DATA_MODE` / keep `RISKFORGE_HISTORICAL_DATASET` as-is (AD-A13)

### G8
- Hostile tests + `reviews/wave-a-real-data-hostile-review.md`
- Update `docs/known_limitations.md` (currently: “No live market-data vendor integration”)

## Collision risks

1. **`MarketDataProvider` vs public providers** — different jobs. Keep public HTTP in `app.market.ingestion`.
2. **`MarketSnapshot.content_hash` vs Wave A content hash** — snapshot hash excludes id/as_of; series hash must exclude `retrieved_at`. Do not merge them.
3. **Dataset factory aliases** — `resolve_dataset_source` fails closed on unknown ids. Public frozen ids must be registered explicitly.
4. **Rate units** — FRED DGS* are percent levels; snapshot wants 4.25 → 0.0425; history wants 4.25 → 4.30 = +5 bp. Convert once at freeze (AD-A10). Reuse `shock_units`.
5. **Uncommitted frontend theme/overview work** — do not `git add -A`. Do not rewrite `Overview.jsx` / `styles.css` for Wave A until G6, and then only additive nav/data surfaces.
6. **CI network** — adapters must default to injected `httpx.Client` so tests pass with `respx`/mock transport; no live Yahoo/FRED in CI.
7. **Secrets** — FRED key via env only; never in provenance, logs, or frontend payloads (AD-A14).

## Wave A provider selection (A1.4 lock)

| Role | Provider | Access | Credentials | Testability |
|---|---|---|---|---|
| Equity/ETF search + daily history | Yahoo Finance public JSON (`query1.finance.yahoo.com`) | Unofficial public EOD/search; not a licensed vendor feed | None | Fixture HTTP via `httpx` mock; adjusted close from chart `adjclose` |
| USD rates/macro | FRED API (`api.stlouisfed.org`) | Official public series | `FRED_API_KEY` env only | Fixture JSON; missing obs are `"."` |

Claims: **public EOD / public FRED series**, not institutional vendor infrastructure.

## Suggested implementation order (already in TRACKER)

G1 models+protocols+adapters+offline tests → G2 catalog → G3 quality/hash → G4 freeze history into existing dataset/panel → G5 snapshot builder → G6 API/UI → G7 optional demo → G8 hostile+CI.

## Out of scope (reject if proposed)

Streaming ticks, Kafka, data lake, global security master, corporate actions, second VaR engine, frontend provider calls, Bloomberg/Refinitiv, live-network CI.
