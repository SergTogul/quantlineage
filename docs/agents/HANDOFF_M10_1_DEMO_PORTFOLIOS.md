# Handoff — M10.1 Demo portfolios

## Task
M10.1 — Demo portfolios (Equity Vol / Rates Macro / Cross-Asset)

## Owner
Lead Architect / Orchestrator (+ Market Data for snapshot-from-positions seeding; no PricingEngine changes)

## Summary
- Expanded in-code demo books to three themed portfolios: `equity-vol`, `rates-macro`, `global-macro` (Cross-Asset theme).
- `SAMPLE_PORTFOLIO` remains the Cross-Asset book (`id=global-macro`, name `Global Macro Demo`) for DI / default `GET /portfolio` / E2E compatibility.
- Catalog helpers + dual-mounted `GET /portfolios` and `GET /portfolios/{id}`; SQLAlchemy seed inserts all three demos when `RISKFORGE_DATABASE_URL` is set.
- No live market vendor feeds. PricingEngine seams untouched.
- Milestone 10 stays **PARTIAL** (M10.2 / M10.3 still open).

## Files changed
- `backend/app/sample.py` — three themed portfolios + catalog summaries
- `backend/app/api/portfolio.py` — list/get demo portfolio routes
- `backend/app/api/legacy_deprecation.py` — `/portfolios` legacy root
- `backend/app/persistence/wiring.py` — seed all `DEMO_PORTFOLIOS`
- `backend/tests/test_demo_portfolios.py` — new
- `backend/tests/test_api_router_decomposition.py` — critical paths
- `backend/tests/test_api_v1_compatibility.py` — dual-mount paths
- `backend/tests/test_api_legacy_deprecation.py` — `/portfolios` headers
- `ROADMAP.md` — M10 PARTIAL; M10.1 DONE
- `docs/agents/HANDOFF_M10_1_DEMO_PORTFOLIOS.md` — this file

## Public/interface changes
- **New** (dual-mount `/api/v1` + legacy):
  - `GET /portfolios` → `list[DemoPortfolioSummary]`
  - `GET /portfolios/{portfolio_id}` → `Portfolio` (404 `{code,message,details}` if unknown)
- Default `GET /portfolio` unchanged (still Cross-Asset sample)
- Persistence: SQLAlchemy seed now upserts all three demo portfolio ids when missing

## Numerical conventions
- Units: synthetic embedded marks only (no vendor series)
- Sign convention: N/A (composition / catalog task)
- Tolerances/reference: Builtin pricing must return finite MVs; portfolio MV abs sum > 0

## Tests added/updated
- `test_demo_portfolios.py`: theme composition, catalog order, priceability, list/get API, SQLAlchemy seed of all three
- Dual-mount / legacy / router critical-path coverage for `/portfolios`

## Commands executed
```bash
cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=builtin .venv/bin/python -m pytest \
  tests/test_demo_portfolios.py tests/test_api_router_decomposition.py \
  tests/test_api_v1_compatibility.py tests/test_api_legacy_deprecation.py \
  tests/test_persistence_di.py -q --tb=short
# → 46 passed, 1 Starlette/httpx warning

cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest \
  tests/test_demo_portfolios.py tests/test_next_phase.py tests/test_persistence_di.py \
  tests/test_api.py tests/test_api_router_decomposition.py \
  tests/test_api_v1_compatibility.py tests/test_api_legacy_deprecation.py \
  tests/test_hierarchy.py -q --tb=line
# → 74 passed, 1 warning

.venv/bin/ruff check app/sample.py app/api/portfolio.py app/api/legacy_deprecation.py \
  app/persistence/wiring.py tests/test_demo_portfolios.py
# → All checks passed
```

## Results
- Backend: focused + affected suite **74 passed** (1 known Starlette/httpx deprecation warning)
- Frontend: unchanged
- QuantLib: used for broader suite (`RISKFORGE_PRICING_ENGINE=quantlib`)
- C++: N/A
- Build: N/A
- Milestone 10: **PARTIAL** (M10.1 DONE only)

## Known limitations / risks
- UI still loads default Cross-Asset book only (no portfolio picker wired to `/portfolios`)
- Default market snapshot seed still derived from Cross-Asset marks only (not per-theme snapshots)
- M10.2 historical dataset and M10.3 deterministic scripts not started

## Follow-up / next owner
- Owner: Market Data (+ Lead Architect) — **M10.2** demo historical market dataset (replace or wire `data/sample_portfolio.csv`)
- Requested action: reproducible factor-return / snapshot history for VaR replay demos; no live vendors
- Blocking?: no
