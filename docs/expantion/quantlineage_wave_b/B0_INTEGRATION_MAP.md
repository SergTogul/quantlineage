# Wave B — B0 Integration Map

Inspected on `master` @ `e2ebe67` (Wave A G8 DONE, CI green).

## Reuse (do not rebuild)

| Concern | Reuse |
|---|---|
| Frozen identities | `RiskRun.historical_dataset_id/version`, `market_snapshot_id`, `as_of`, `portfolio_version` |
| Historical VaR/ES | `HistoricalRiskEngine.calculate()` — **not** a new VaR engine |
| Factor panel | `HistoricalFactorPanel` / `create_historical_dataset` (demo + `real:public:wave-a`) |
| Flagship risk-change | `POST /api/v1/risk/runs/compare` → `RiskChangeReport` (`risk_run_compare.py`). Residual always present. Frontend: `compareRiskRuns`, `RiskChangeAttribution` |
| Portfolio-pair waterfall | `POST /api/v1/risk/change-attribution` (keep; G4 hero is the **RiskRun pair** compare) |
| Contributors | `POST /api/v1/risk/contributors`, `POST /api/v1/risk/es` |
| KR-DV01 / rates | `GET /api/v1/market/rates-showcase` (`build_rates_showcase`); `RatesShowcase` UI already charts API values only |
| Dashboard | `POST /api/v1/risk/dashboard` |
| Wave A benchmark name | curated `equity:US:SPY` / factor `EquitySpot:SPY` |
| Frontend client | `frontend/src/api.js` `/api/v1` only |

## Missing (Wave B must add)

There is **no** backend historical-analytics result today: no cumulative/wealth series, annualized return, annualized vol, max drawdown series, rolling vol, Sharpe, best/worst windows, or benchmark beta/TE. Grep hits for “drawdown/sharpe” are crisis copy or “not cumulative” scenario comments.

`HistoricalRiskEngine` P&L paths are **independent shocked snapshots**, not a wealth index. B1 must compute analytics from frozen history + portfolio/snapshot identity without calling providers.

## UI today

`App.jsx` sections: overview, market-data, analytics (rates + provenance + risk-change waterfall). No Historical Analytics page. G5 adds one coherent page; G3/G4 consume existing risk artifacts.

## Invariants

- Backend owns all financial math (AD-B1).
- One canonical analytics result powers summary + charts (AD-B3).
- Range changes create **new** requests; they do not mutate frozen CSV/snapshots (AD-B10).
- Synthetic and Wave A public data share the same analytics path (AD-B11).
- Frontend may format/sort/chart only.
- No optimizer / retirement / efficient-frontier scope.
