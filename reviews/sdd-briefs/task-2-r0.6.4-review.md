# Task 2 Review — R0.6.4 Remove anti-cache behavior

**Base:** `35bf9fa`  
**Head:** `68c302a`  
**Diff reviewed:** `.superpowers/sdd/review-35bf9fa..68c302a.diff`  
**Brief:** `reviews/sdd-briefs/task-2-r0.6.4-brief.md`  
**Implementer report (unverified claims):** `reviews/sdd-briefs/task-2-r0.6.4-report.md`

## Verdict

| Gate | Result |
|---|---|
| Spec compliance | ✅ |
| Task quality | **Approved** |
| Critical | 0 |
| Important | 0 |
| Minor | 4 |
| RF-007 | Stays **IN PROGRESS** (correct; do not close) |

Ready to proceed to the next RF-007 slice. No blocking fixes required for this task gate.

---

## Spec compliance

Checked against the task brief and binding global constraints.

| Requirement | Evidence in diff | Status |
|---|---|---|
| Identify valuation LRU / `CachedPricingEngine` on unique-shock / full-reval paths | `CachedPricingEngine.value` is the per-snapshot NPV LRU; production loops identified in `historical.py`, `var.py`, `es.py` | Met |
| Bypass or disable LRU for unique-shock / FULL_REVALUATION (or cache at a level that hits) | `bypass_valuation_lru` ContextVar; `value()` returns inner before hash/get/put; shocked loops wrapped; base PV left outside the context | Met |
| Do not cache stale market state (consistent with R0.6.3) | Bypass never serves an LRU NPV; shocked path always calls `_inner.value` with the current snapshot; base keys still bind `content_hash` | Met |
| Numerical identity vs goldens / cold path | `test_unique_shock_full_reval_matches_uncached_inner` and unit-equity `[-100, 0, 50]` at abs `1e-12`; no methodology ADR; existing goldens not rewritten | Met |
| Test that unique-shock full-reval does not populate/consult a miss-only LRU | Spy on `OrderedDict.get` + `valuation_cache_key`; `inner.calls == 1 + n_obs`, `size == 1`, `hits == 0` (zero-shock no longer a false hit) | Met |
| FINDINGS RF-007 stays IN PROGRESS; milestone § R0.6.4 COMPLETE pending review | Status line still **IN PROGRESS** / “Do not close”; § R0.6.4 titled COMPLETE pending review | Met |
| Write `reviews/r0.6.4-anti-cache-report.md` | Added in the same commit | Met |
| One focused commit (`feat(r0.6): ...`); no C++ / no RF-007 close | Single commit `68c302a`; native kernels untouched | Met |
| Preserve interfaces; LLM does not invent numbers; no native kernel expansion | `PricingEngine.value` signature unchanged; no DTO/API change; Python-side cache policy only | Met |
| Behavior change has tests in the same change | New `backend/tests/test_pricing_anti_cache.py` (8 tests) in the owning commit | Met |

Intentional, documented scope limits (still in-scope for this slice):

- Curve-construction LRU left enabled (can hit when rate marks are unchanged).
- Reverse-stress / hierarchy / StressEngine `value()` on unique snaps still use the NPV LRU unless they enter the bypass or `shocked_value`.
- Zero-shock historical observations now reprice instead of hitting the base LRU entry; numbers unchanged.

That matches the brief’s execution-class bypass more than a global cache disable or an RF-007 close.

---

## Strengths

- Correct performance model: unique shocked snapshots cannot hit a per-snapshot identity LRU, so skipping hash/get/put (not merely missing) is the right fix. Base PV stays on the LRU, which is the path that actually hits.
- Bypass is fail-closed on stale NPV: shocked markets always go to the inner engine with the current `MarketSnapshot`.
- Production FULL_REVALUATION sites are wired, not just the helper: `full_revaluation_pnl_series`, `full_revaluation_pnl_from_panel`, `VaRAnalytics._full_reval_position_pnls` (historical and panel iterators), and both ES factor-isolated full-reval loops. Base valuation is computed *outside* the context in each case.
- Tests prove the interesting regression: a zero-shock observation used to be an LRU hit (`inner.calls == 3` vs `4`); they pin `1 + n_obs` inner calls plus golden P&L.
- Process hygiene: RF-007 left open; milestone marked complete *pending review*; no C++ / no SLA invention; QuantLib reuse from Task 1 untouched.

---

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

None.

### Minor (Nice to Have)

1. **ES and panel full-reval bypass untested with spies**  
   - File: `backend/tests/test_pricing_anti_cache.py`  
   - Historical `full_revaluation_pnl_series` and dataset VaR are spy-pinned; `full_revaluation_pnl_from_panel` and ES `_aggregate_factor_pnl_full_reval*` are wired the same way but have no get/key-count pin.  
   - Why it matters: a later edit could drop the `with bypass_valuation_lru()` from ES/panel without failing the new suite. `test_es_contributions.py` only guards numbers.  
   - Fix (optional follow-up): one spy case on panel series and/or ES isolated reval, reusing the existing get + `valuation_cache_key` helpers.

2. **Caller-opt-in ContextVar is easy to miss on later loops**  
   - File: `backend/app/pricing/cache.py` (`bypass_valuation_lru`); call sites in `historical.py` / `var.py` / `es.py`  
   - Bypass is process-context global and must be entered by each unique-shock loop. R0.6.5 process workers will not inherit the flag unless they enter it themselves.  
   - Why it matters: a new FULL_REVALUATION loop that calls `value()` / `value_portfolio()` on shocked snaps silently pays the anti-cache tax again.  
   - Fix: keep the helper in the anti-cache report’s “must wrap” list for R0.6.5; consider a named `value_uncached` on `CachedPricingEngine` if more call sites appear.

3. **`valuation_lru_bypassed()` is unused**  
   - File: `backend/app/pricing/cache.py`  
   - Public helper is never read by tests or production. Tests spy `OrderedDict.get` / `valuation_cache_key` instead.  
   - Why it matters: dead API surface; easy to assume tests already assert it.  
   - Fix: use it in one bypass-path assertion, or drop it until a caller needs it.

4. **Risk engines import the concrete cache module**  
   - Files: `backend/app/risk/historical.py`, `var.py`, `es.py`  
   - Portfolio-risk loops depend on `app.pricing.cache.bypass_valuation_lru` rather than a pricing-interface hook. Harmless when the cache wrapper is off (ContextVar is a no-op).  
   - Why it matters: a second valuation cache wrapper would have to honor the same ContextVar; the coupling is the coordination the brief allowed, but it is still an implementation leak into risk.  
   - Fix: leave as-is for this slice; if another cache appears, lift the flag onto `PricingEngine` or a tiny execution-class helper owned with the cache.

---

## Recommendations

- Accept R0.6.4 and keep RF-007 open through R0.6.5–R0.6.6 / close gate.
- Do not treat this slice as closing N×S pricing cost; FINDINGS/milestone text already states that correctly.
- Optional hardening: spy ES/panel bypass; remind R0.6.5 workers to enter `bypass_valuation_lru` (ContextVar does not cross processes).
- Hierarchy / StressEngine unique-snap `value()` remains an anti-cache pattern of a different execution class; out of scope here, not a reason to reopen this task.

---

## Assessment

**Spec compliance:** ✅  

**Task quality:** Approved  

**Issue counts:** Critical 0 / Important 0 / Minor 4  

**RF-007:** Remains **IN PROGRESS** — implementer correctly did not close it; controller must not close until independent close-gate APPROVE after remaining slices.

**Reasoning:** Diff matches the brief’s unique-shock LRU bypass, preserves numerical methodology, proves the miss-only get/put tax is skipped on the main full-reval path, and updates FINDINGS/milestone/report as required. Remaining gaps are coverage and opt-in hygiene, not blocking defects.
