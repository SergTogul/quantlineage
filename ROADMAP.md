# RiskForge roadmap

Production-style multi-asset portfolio and derivatives risk platform. **QuantLib prices; RiskForge owns portfolio risk.**

## Milestone 0 — Local runnable baseline (done)

- [x] Python 3.12 backend venv, pinned requirements, QuantLib import
- [x] `pytest` with `RISKFORGE_PRICING_ENGINE=quantlib` — no QuantLib skips
- [x] Frontend `npm test` / `npm run build`
- [x] API smoke: `GET /health` → 200
- [x] Git repo + this roadmap

## Milestone 1 — Quant correctness foundation

**Pricing (QuantLib adapters)**

- [ ] EquityFuture, FXForward, FXOption (+ reference comparison tests)
- [ ] Later: IR future, cap/floor, swaption
- [ ] Keep `PricingEngine` seam; no QuantLib types outside adapters

**Market data**

- [ ] Structured `MarketSnapshot` (equity, rates, vol, FX sub-markets)
- [ ] `snapshot.bump(factor, amount)` and `snapshot.diff(other)`
- [ ] Stress path: base snapshot → scenario → shocked snapshot → reval

**Curves & surfaces**

- [ ] USD OIS discount + SOFR projection; EUR/GBP
- [ ] Bootstrap, interpolation, tenor nodes, curve/key-rate shifts (1Y–30Y)
- [ ] Equity/FX vol surfaces (expiry × strike); vega by bucket

**Risk factors & sensitivities**

- [ ] Typed `RiskFactor` IDs and `RiskVector`
- [ ] Bump-and-revalue: delta, gamma, vega, DV01, key-rate DV01, FX delta

**Historical VaR**

- [ ] Historical factor dataset (returns / rate moves / vol moves)
- [ ] Full-revaluation VaR modes: `LINEAR`, `DELTA_GAMMA`, `FULL_REVALUATION`
- [ ] Expected Shortfall with position/desk/factor contributions

## Milestone 2 — Portfolio risk & stress depth

- [ ] Incremental / marginal / component VaR; `POST /risk/what-if`
- [ ] Stress Engine v3: rich scenario schema, combined multi-factor shocks
- [ ] Historical crisis presets (2008, COVID, 2022 rates, etc.; label approximations)
- [ ] Reverse stress: breach-level solving (single- and multi-factor)
- [ ] Stress loss decomposition (desk / strategy / factor)
- [ ] P&L explain upgrades tied to structured market diffs

## Milestone 3 — Performance & infrastructure

- [ ] C++ scenario kernel benchmarks and production wiring
- [ ] CI (backend + frontend + optional native build)
- [ ] Docker / deployment hardening; optional Postgres for portfolios
- [ ] API versioning and router split

## Milestone 4 — Terminal UI & AI layer

- [ ] React terminal polish (hierarchy drill-down, ES/stress contributions)
- [ ] E2E tests (Playwright); MSW/RTL for API-bound UI
- [ ] LLM tool layer over deterministic `POST /risk/query`
- [ ] Interview-grade demos and documentation

## Architectural invariant

Pricing library prices instruments. RiskForge aggregates, scenarios, limits, attribution, and compute — without leaking QuantLib into domain or API layers.
