# Handoff — Demo historical market dataset

## Task
 — Demo historical market dataset (synthetic/replay factor history)

## Owner
Market Data & Curves Engineer (+ Backend/API DI wiring in `deps.py` / `PortfolioService`)

## Summary
- Shipped packaged CSV `data/demo_historical_factors.csv` (750 observations) as a frozen replay of `SyntheticHistoricalDataset(seed=7, observations=750)` — **no live vendor feeds**.
- Added CSV loaders + factory (`create_historical_dataset`) with env `QUANTLINEAGE_HISTORICAL_DATASET=demo|synthetic|/path.csv`.
- API DI defaults to the demo CSV; `HistoricalRiskEngine(dataset=None)` still constructs synthetic RNG for ctor backward compatibility.
- `PortfolioService` shares the injected engine's dataset with `VaRAnalytics` / `ESContributionAnalytics` / related engines.
- Removed unused orphan `data/sample_portfolio.csv` (superseded by in-code portfolios).
- PricingEngine seams untouched. Workstream 10 stays **PARTIAL** ( open).

## Files changed
- `backend/app/risk/historical_data.py` — CSV / demo / factory loaders
- `backend/app/api/deps.py` — wire `create_historical_dataset` into `HistoricalRiskEngine`
- `backend/app/services/portfolio_service.py` — share dataset across analytics engines
- `backend/tests/test_demo_historical_dataset.py` — new
- `data/demo_historical_factors.csv` — packaged demo series
- `data/README.md` — how to load
- `data/sample_portfolio.csv` — deleted (orphan)
- `README.md` — demo data section
- `ROADMAP.md` — DONE; workstream still PARTIAL
- `docs/agents/HANDOFF_DEMO_HISTORICAL_DATASET.md` — this file

## Public/interface changes
- **New** Python APIs: `load_factor_observations_csv`, `load_csv_historical_dataset`, `load_demo_historical_dataset`, `demo_historical_dataset_path`, `create_historical_dataset`, `FileHistoricalDataset`, `DEMO_HISTORICAL_DATASET_ID`
- **New** env: `QUANTLINEAGE_HISTORICAL_DATASET` (`demo` default for factory / API DI)
- No new HTTP routes; risk APIs consume the dataset via DI
- No PricingEngine interface changes

## Numerical conventions
- Units: equity/FX relative returns; vol relative level moves; rates parallel bp moves (same as )
- Sign convention: as `FactorObservationSeries`
- Tolerances/reference: exact float round-trip (`repr`) vs `SyntheticHistoricalDataset(seed=7, observations=750)`; VaR dict equality for demo vs seed-7 engine

## Tests added/updated
- `test_demo_historical_dataset.py`: CSV load/validation, demo path, determinism, synthetic parity, factory/env, VaR/scenario consumption, API DI parity

## Commands executed
```bash
cd backend && PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=builtin .venv/bin/python -m pytest \
 tests/test_demo_historical_dataset.py tests/test_historical_data.py \
 tests/test_scenarios.py tests/test_var_methodology.py tests/test_api.py \
 tests/test_api_router_decomposition.py tests/test_api_v1_compatibility.py \
 tests/test_demo_portfolios.py tests/test_component_var.py tests/test_marginal_var.py \
 -q --tb=line
# → 77 passed, 1 Starlette/httpx warning

cd backend && PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest \
 tests/test_demo_historical_dataset.py tests/test_historical_data.py \
 tests/test_api.py tests/test_next_phase.py -q --tb=line

.venv/bin/ruff check app/risk/historical_data.py app/api/deps.py \
 app/services/portfolio_service.py tests/test_demo_historical_dataset.py
# → All checks passed
```

## Results
- Backend: focused + affected suite **77 passed** (builtin); QuantLib smoke **32 passed**
- Frontend: unchanged
- QuantLib: smoke green
- C++: N/A
- Build: N/A
- Workstream 10: **PARTIAL** ( DONE; open)
- Push: SHA `0ab59cb` on `origin/master` (https://github.com/SergTogul/quantlineage)

## Known limitations / risks
- Aggregate factors only (no per-tenor key-rate history in the CSV)
- Optional `date` column is documentary; engines do not time-align by calendar
- Default API source is now file-backed demo (numerically = prior seed-7 synthetic); override with `QUANTLINEAGE_HISTORICAL_DATASET=synthetic` if needed
- deterministic demo scripts not started

## Follow-up / next owner
- Owner: Lead Architect / Backend (+ QA as needed) — Deterministic demo scripts
- Requested action: reproducible CLI/scripts that load demo portfolios + historical dataset and emit fixed VaR/stress artifacts for demos
- Blocking?: no
