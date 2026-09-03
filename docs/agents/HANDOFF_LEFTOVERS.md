# Handoff: Open leftovers inventory (excl. )

**Date:** 2026-09-02 (refreshed)
**Owner:** Lead Architect / Orchestrator
**Source:** `ROADMAP.md` Progress + highest-risk gaps + open `[ ]` / PARTIAL items
**Do not start:** Workstream 11, Workstream 12 (POSTPONED until Lead/user unblocks)

This note avoids editing `ROADMAP.md` (may be mid-edit by another agent). Treat ROADMAP as authoritative if it diverges.

---

## Workstream rollup (current truth)

| Workstream | Status |
|-----------|--------|
| | **COMPLETE** |
| | **DONE** (valuation LRU + curve-construction + scenario memo) |
| | **COMPLETE** + formal scenario-kernel SLA-K1/K2 (`benchmarks/RESULTS.md`) |
| | **DONE** (`docs/methodology/multi_factor_reverse_stress.md`) |
| | **DONE** (tenor KR DV01 on limit drill-down) |
| | **DONE** (Builtin/QL ZC bond day-count parity) |
| | **DONE** (e2e reverse-stress heading / testid hardening) |
| | **FIX PUSHED** (`11339c6`); GHA URL confirm pending (invalid `gh` keyring — do not spam login) |
| | **POSTPONED** — do not implement |
| | **NOT STARTED** |

---

## Recently closed (do not re-open)

| ID | Item | Evidence hint |
|----|------|---------------|
| | Builtin vs QL ZC bond day-count / compounding | `HANDOFF_BOND_DAYCOUNT.md`; SHA `f39ba6a` |
| | KR DV01 limit drill-down → tenor KR | `HANDOFF_KEY_RATE_LIMIT_DRILLDOWN.md` |
| | Curve-construction cache + scenario memo | `HANDOFF_PRICING_CACHE.md` |
| ** SLA** | Scenario-kernel SLA-K1/K2 (Option B reversed) | `HANDOFF_SCENARIO_KERNEL_SLA.md`; not HTTP VaR wall-time |
| | Multi-factor reverse methodology doc | `HANDOFF_AI_DOCS_POSTPONED_REVERSE_STRESS_DOC.md` |
| | e2e-playwright reverse-stress collision | `HANDOFF_CI_TRIAGE.md` |
| | Demo portfolios + historical dataset + deterministic scripts | `HANDOFF_DEMO_PORTFOLIOS.md`, `HANDOFF_DEMO_HISTORICAL_DATASET.md`, `HANDOFF_DETERMINISTIC_DEMO_SCRIPTS.md` |
| Vitest lib migrate | `*.mjs` → Vitest | `HANDOFF_VITEST_LIB_MIGRATE.md` |
| Demo artifact float CI | Cross-platform float stabilize | `HANDOFF_DEMO_ARTIFACT_FLOAT_CI.md` |

---

## (A) Completable polish (non-blocking)

| ID | Item | Owner hint | Notes |
|----|------|------------|-------|
| | Record green GHA URL for mypy fix | DevOps / operator | Fix on master; `gh` keyring invalid — repair offline, then check the ROADMAP box. No product code. |
| residual | Broaden RTL/MSW to more panels | Frontend / QA | COMPLETE; non-blocking |
| residual | Gradual Ruff/mypy enable (pay down ignores) | DevOps / Backend | Staged gate already green; non-blocking |

## (B) Product decisions (do not implement until decided)

| ID | Item | Notes |
|----|------|-------|
| | AI assistant; docs & portfolio presentation | **POSTPONED** — do not start |
| gate | Legacy unversioned path removal | Earliest **2027-03-02**; needs Lead approval |
| timing | Final portfolio demo | NOT STARTED; depends on demo narrative / postponed docs |

### Accepted PARTIAL (product decision recorded)

| Item | Notes |
|------|-------|
| *(none for )* | SLA **COMPLETE** — SLA-K1/K2 in `benchmarks/RESULTS.md`; do not reopen Option B |

## (C) Deferred explicitly (accepted residuals)

| Item | Notes |
|------|-------|
| **Redis/RQ** | Fair scheduling / ops queue; claim safety via Postgres `SKIP LOCKED` (ADR 005 / ). Do not add empty ceremony |
| FULL_REVALUATION native kernel | By design stays Python / PricingEngine |
| IR future full QL FRA | Algebraic STIR accepted; richer FRA deferred |
| Multi-factor reverse global optimum | Ray + coordinate descent; methodology at `docs/methodology/multi_factor_reverse_stress.md` |
| Caps/floors/swaptions; surface grid bumps; QL smile | Tracked as below |

## (D) Large deferred features

| ID | Item | Owner hint |
|----|------|------------|
| | Caps / floors / swaptions (IR vol + exercise) | Quant Pricing |
| | Surface-aware EquityVol/FXVol bumps rewrite grids | Market Data (+ Pricing) |
| | QL full surface / smile (`BlackVarianceSurface` etc.) | Quant Pricing |
| | Curve bootstrap from market instruments | Market Data |
| | Final portfolio demo (seed flow, screenshots, clean-checkout) | Lead + Frontend + QA |

---

## Parallel now (safe 2–3)

Different owners / file sets; **no **; no SLA invention; no Redis ceremony:

1. ** RTL/MSW broaden** — Frontend/QA: more panels with fixtures only (no client risk math)
2. **Ruff/mypy debt pay-down** — DevOps/Backend: remove one ignore class at a time + CI green
3. alone — Quant Pricing epic (multi-session); do **not** parallel with

**Operator (non-code):** repair `gh` keyring once, record green run URL in ROADMAP.

**Do not parallel:** + (same market/pricing blast radius). **COMPLETE** — do not reopen Option B. Do not start .

## Completion report stub

- Summary: leftovers inventory refreshed to post–-SLA / truth; remain POSTPONED; Redis deferred
- Files changed: `docs/agents/HANDOFF_LEFTOVERS.md` (+ optional handoff push-SHA note)
- Tests: n/a (docs-only)
- Handoff: parent may dispatch A-lane polish or D-lane epics per parallel list above
