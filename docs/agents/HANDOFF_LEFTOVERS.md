# Handoff: Open leftovers inventory (excl. M11/M12)

**Date:** 2026-09-02 (refreshed)  
**Owner:** Lead Architect / Orchestrator  
**Source:** `ROADMAP.md` Progress + highest-risk gaps + open `[ ]` / PARTIAL items  
**Do not start:** Milestone 11, Milestone 12 (POSTPONED until Lead/user unblocks)

This note avoids editing `ROADMAP.md` (may be mid-edit by another agent). Treat ROADMAP as authoritative if it diverges.

---

## Milestone rollup (current truth)

| Milestone | Status |
|-----------|--------|
| M0–M10 | **COMPLETE** |
| M5.5 | **DONE** (valuation LRU + curve-construction + scenario memo) |
| M6 | **COMPLETE** + formal scenario-kernel SLA-K1/K2 (`benchmarks/RESULTS.md`) |
| M3.9 | **DONE** (`docs/methodology/multi_factor_reverse_stress.md`) |
| M4.7 | **DONE** (tenor KR DV01 on limit drill-down) |
| M1.12 | **DONE** (Builtin/QL ZC bond day-count parity) |
| M9.11 | **DONE** (e2e reverse-stress heading / testid hardening) |
| M9.12 | **FIX PUSHED** (`11339c6`); GHA URL confirm pending (invalid `gh` keyring — do not spam login) |
| M11 / M12 | **POSTPONED** — do not implement |
| M13 | **NOT STARTED** |

---

## Recently closed (do not re-open)

| ID | Item | Evidence hint |
|----|------|---------------|
| **M1.12** | Builtin vs QL ZC bond day-count / compounding | `HANDOFF_M1_12_BOND_DAYCOUNT.md`; SHA `f39ba6a` |
| **M4.7** | KR DV01 limit drill-down → tenor KR | `HANDOFF_M4_7.md` |
| **M5.5** | Curve-construction cache + scenario memo | `HANDOFF_M5_5_CACHE.md` |
| **M6 SLA** | Scenario-kernel SLA-K1/K2 (Option B reversed) | `HANDOFF_M6_SLA.md`; not HTTP VaR wall-time |
| **M3.9** | Multi-factor reverse methodology doc | `HANDOFF_M11_M12_POSTPONED_M39.md` |
| **M9.11** | e2e-playwright reverse-stress collision | `HANDOFF_M911_CI_TRIAGE.md` |
| **M10** | Demo portfolios + historical dataset + deterministic scripts | `HANDOFF_M10_*` |
| M9 Vitest lib migrate | `*.mjs` → Vitest | `HANDOFF_M9_VITEST_LIB_MIGRATE.md` |
| Demo artifact float CI | Cross-platform float stabilize | `HANDOFF_DEMO_ARTIFACT_FLOAT_CI.md` |

---

## (A) Completable polish (non-blocking)

| ID | Item | Owner hint | Notes |
|----|------|------------|-------|
| **M9.12** | Record green GHA URL for mypy fix | DevOps / operator | Fix on master; `gh` keyring invalid — repair offline, then check the ROADMAP box. No product code. |
| M9 residual | Broaden RTL/MSW to more panels | Frontend / QA | M9 COMPLETE; non-blocking |
| M9 residual | Gradual Ruff/mypy enable (pay down ignores) | DevOps / Backend | Staged gate already green; non-blocking |

## (B) Product decisions (do not implement until decided)

| ID | Item | Notes |
|----|------|-------|
| **M11 / M12** | AI assistant; docs & portfolio presentation | **POSTPONED** — do not start |
| M7.6 gate | Legacy unversioned path removal | Earliest **2027-03-02**; needs Lead approval |
| M13 timing | Final portfolio demo | NOT STARTED; depends on demo narrative / postponed docs |

### Accepted PARTIAL (product decision recorded)

| Item | Notes |
|------|-------|
| *(none for M6)* | M6 SLA **COMPLETE** — SLA-K1/K2 in `benchmarks/RESULTS.md`; do not reopen Option B |

## (C) Deferred explicitly (accepted residuals)

| Item | Notes |
|------|-------|
| **Redis/RQ** | Fair scheduling / ops queue; claim safety via Postgres `SKIP LOCKED` (ADR 005 / M5.7). Do not add empty ceremony |
| FULL_REVALUATION native kernel | By design stays Python / PricingEngine |
| IR future full QL FRA | Algebraic STIR accepted; richer FRA deferred |
| Multi-factor reverse global optimum | Ray + coordinate descent; methodology at `docs/methodology/multi_factor_reverse_stress.md` (M3.9) |
| Caps/floors/swaptions; surface grid bumps; QL smile | Tracked as M1.9–M1.11 below |

## (D) Large deferred features

| ID | Item | Owner hint |
|----|------|------------|
| **M1.9** | Caps / floors / swaptions (IR vol + exercise) | Quant Pricing |
| **M1.10** | Surface-aware EquityVol/FXVol bumps rewrite grids | Market Data (+ Pricing) |
| **M1.11** | QL full surface / smile (`BlackVarianceSurface` etc.) | Quant Pricing |
| **M1.13** | Curve bootstrap from market instruments | Market Data |
| **M13** | Final portfolio demo (seed flow, screenshots, clean-checkout) | Lead + Frontend + QA |

---

## Parallel now (safe 2–3)

Different owners / file sets; **no M11/M12**; no SLA invention; no Redis ceremony:

1. **M9 RTL/MSW broaden** — Frontend/QA: more panels with fixtures only (no client risk math)  
2. **Ruff/mypy debt pay-down** — DevOps/Backend: remove one ignore class at a time + CI green  
3. **M1.9** alone — Quant Pricing epic (multi-session); do **not** parallel with M1.10/M1.11  

**Operator (non-code):** repair `gh` keyring once, record M9.12 green run URL in ROADMAP.

**Do not parallel:** M1.10 + M1.11 (same market/pricing blast radius). M6 **COMPLETE** — do not reopen Option B. Do not start M11/M12.

## Completion report stub

- Summary: leftovers inventory refreshed to post–M1.12 / M4.7 / M5.5 / M6-SLA / M3.9 / M9.11–12 / M10 truth; M11/M12 remain POSTPONED; Redis deferred  
- Files changed: `docs/agents/HANDOFF_LEFTOVERS.md` (+ optional M1.12 handoff push-SHA note)  
- Tests: n/a (docs-only)  
- Handoff: parent may dispatch A-lane polish or D-lane epics per parallel list above  
