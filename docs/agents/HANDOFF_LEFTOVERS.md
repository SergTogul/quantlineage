# Handoff: Open leftovers inventory (excl. M11/M12)

**Date:** 2026-09-02  
**Owner:** Lead Architect / Orchestrator  
**Source:** `ROADMAP.md` Progress + highest-risk gaps + open `[ ]` / PARTIAL items  
**Do not start:** Milestone 11, Milestone 12 (POSTPONED)

This note avoids editing `ROADMAP.md` (may be mid-edit by another agent). Treat ROADMAP as authoritative if it diverges.

---

## (A) Completable polish (M5.5-class)

| ID | Item | Owner hint | Notes |
|----|------|------------|-------|
| **M5.5** | Curve-construction cache and/or scenario-engine memo | Backend/API | Valuation LRU DONE; milestone COMPLETE; non-blocking |
| **M4.7** | KR DV01 limit drill-down → tenor KR (not parallel `dv01`) | Portfolio Risk (+ Backend) | `limit_drilldown.py` maps `key_rate_dv01` → `dv01` |
| M9 residual | Migrate leftover `*.mjs` Vitest; broaden RTL/MSW | Frontend / QA | Explicitly non-blocking for M9 COMPLETE |
| M9 residual | Gradual Ruff/mypy enable | DevOps / Backend | Non-blocking staged gate follow-up |
| M1.12 | Builtin vs QL ZC bond day-count / compounding | Quant Pricing | Close gap **or** tighten docs/tolerances |

## (B) Product decisions (do not implement until decided)

| ID | Item | Notes |
|----|------|-------|
| M7.6 gate | Legacy unversioned path removal | Earliest **2027-03-02**; needs Lead approval |
| M13 timing | Final portfolio demo | NOT STARTED; depends on demo narrative / postponed docs |

### Accepted PARTIAL (product decision recorded)

| Item | Notes |
|------|-------|
| **M6 SLA** | Option B 2026-09-02: no product VaR wall-time SLA; M6 stays **PARTIAL**; `docs/agents/HANDOFF_M6_SLA.md` |

## (C) Deferred explicitly (accepted residuals)

| Item | Notes |
|------|-------|
| **Redis/RQ** | Fair scheduling / ops queue; claim safety via Postgres `SKIP LOCKED` (ADR 005 / M5.7). Do not add empty ceremony |
| FULL_REVALUATION native kernel | By design stays Python / PricingEngine |
| IR future full QL FRA | Algebraic STIR accepted; richer FRA deferred |
| Multi-factor reverse global optimum | Ray + coordinate descent; methodology at `docs/methodology/multi_factor_reverse_stress.md` (M3.9) |

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

Different owners / file sets; no M11/M12; no SLA invention:

1. **M5.5** — Backend/API: curve and/or scenario memo + invalidation tests  
2. **M4.7** — Portfolio Risk: tenor KR contributors in limit drill-down + tests  
3. **M1.12** *or* M9 Vitest `*.mjs` migrate — Quant Pricing *or* Frontend/QA (pick one third lane)

**Do not parallel:** M1.10 + M1.11 (same market/pricing blast radius); M1.9 alone is a multi-session epic. M6 SLA disposed (accepted PARTIAL) — do not invent COMPLETE.

## Completion report stub

- Summary: inventory only; no product code  
- Files changed: `docs/agents/HANDOFF_LEFTOVERS.md`  
- Tests: n/a  
- Handoff: parent may dispatch A-lane agents per parallel list above  
