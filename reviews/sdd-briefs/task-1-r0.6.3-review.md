# Task 1 Review — R0.6.3 Reuse QuantLib structures where safe

**Base:** `934379c`  
**Head:** `35bf9fa`  
**Diff reviewed:** `.superpowers/sdd/review-934379c..35bf9fa.diff`  
**Brief:** `reviews/sdd-briefs/task-1-r0.6.3-brief.md`  
**Implementer report (unverified claims):** `reviews/sdd-briefs/task-1-r0.6.3-report.md`

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
| Safe QuantLib reuse on shocked full-reval (quotes / handles / terms / schedules; no stale market state) | `_ReusableScalarOption` + live `SimpleQuote` updates; terms cache; swap schedule cache; surfaces/curves still rebuilt from current snapshot | Met |
| Numerical identity vs pre-change / cold path | `test_scalar_option_full_reval_reuse_matches_cold_valuations` at abs `1e-12`; no methodology ADR | Met |
| Document reused vs rebuilt | `reviews/r0.6.3-quantlib-reuse-report.md` | Met |
| Tests: parity (+ optional structure spy) | New `backend/tests/test_quantlib_reuse.py` (reuse count + cold parity) | Met |
| FINDINGS RF-007 stays IN PROGRESS; milestone § R0.6.3 COMPLETE pending review | FINDINGS status line updated, still **IN PROGRESS**; milestone titled COMPLETE pending review | Met |
| Reuse report written | `reviews/r0.6.3-quantlib-reuse-report.md` | Met |
| One focused commit; no C++ / no RF-007 close / pricing-only ownership | Single commit `35bf9fa`; touches `quantlib.py` + tests + review docs only | Met |
| Preserve interfaces; LLM does not invent numbers; no native kernel expansion | No `PricingEngine` / API contract changes; Python-side adapter only | Met |

Intentional, documented scope limits (still in-scope for “where safe”):

- Attached vol surfaces and snapshot curve/key-rate handles are rebuilt each valuation.
- Bonds / caps / swaptions / futures / forwards are not structure-cached beyond shared terms caching.
- Swap instruments/curves/fixings still rebuild; only schedules are cached.

That matches the brief’s safety constraint more than a full N×S elimination (which remains later RF-007 work).

---

## Strengths

- Correct safety model: contract/structure keyed by evaluation date + economics; market inputs pushed through `SimpleQuote` before every `NPV()` / Greek read.
- Vol-surface branch preserved: scalar cache only when `_has_matching_vol_surface` is false, matching `_black_vol_handle`’s flat-vol predicate (`raw`, `spot > 0`, `asset_class`).
- Session/`evaluation_date` interaction is sound: cache keys use `self.evaluation_date` inside `_session`, so `as_of`-driven session dates do not reuse the wrong exercise/reference date.
- Tests hit the real full-reval path (`full_revaluation_pnl_series`) rather than only unit-mocking the adapter; RED→GREEN structure-count story is credible from the diff.
- Process hygiene: RF-007 left open; milestone marked complete *pending review*; ownership stayed in Quant Pricing paths.

---

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

None.

### Minor (Nice to Have)

1. **FX / swap reuse untested structurally**  
   - File: `backend/tests/test_quantlib_reuse.py`  
   - Equity `VanillaOption` construction count + P&L parity are covered; FX option reuse and swap schedule hit-rate are implemented in `quantlib.py` but lack a parallel spy/parity fixture.  
   - Why it matters: shared helper lowers risk, but a future edit to `_fx_option` / `_swap_schedules` could regress without a pin.  
   - Fix (optional follow-up): one FX reuse count or cold-parity case; optional schedule construction spy for swaps.

2. **Terms cache key bypasses existing economics key helper**  
   - File: `backend/app/pricing/quantlib.py` (`_terms_key` / `_terms_for_position`)  
   - Uses `type(position).__name__` + full `position.model_dump_json()` instead of `trade_cache_key` / terms economics already maintained in `app/pricing/cache.py`.  
   - Why it matters: correctness is OK for current mark-free Position DTOs, but the key is heavier and can diverge from the project’s established “terms-only” hashing convention (e.g. `duration` on bonds/swaps affects the key without changing `InstrumentTerms`).  
   - Fix: key off `trade_cache_key(position)` or `terms.model_dump_json()` after `terms_from_position`.

3. **Duplicated Valuation packing on option paths**  
   - File: `backend/app/pricing/quantlib.py` (`_option`, `_fx_option`)  
   - Cached scalar early-return and surface fall-through each copy quantity/notional × Greek scaling.  
   - Why it matters: future convention tweaks (vega scaling, cash delta) could drift between branches.  
   - Fix: small private helper that builds `Valuation` from unit Greeks.

4. **Unbounded per-engine structure/terms caches**  
   - File: `backend/app/pricing/quantlib.py` (`__init__` caches)  
   - No eviction; fine for short-lived full-reval engines, weaker if a long-lived process prices many unique contracts.  
   - Why it matters: RSS growth outside the tested N×S pattern.  
   - Fix: document lifetime assumption (already partly in the reuse report) or bound/clear cache at session/run boundaries later if profiling warrants.

---

## Recommendations

- Accept R0.6.3 and keep RF-007 open through R0.6.4–R0.6.6 / close gate.
- Optional hardening before or during later RF-007 work: FX reuse pin + swap schedule spy; align terms cache key with `trade_cache_key`.
- Do not treat this slice as closing N×S pricing cost; milestone text already states that correctly.

---

## Assessment

**Spec compliance:** ✅  

**Task quality:** Approved  

**Issue counts:** Critical 0 / Important 0 / Minor 4  

**RF-007:** Remains **IN PROGRESS** — implementer correctly did not close it; controller must not close until independent close-gate APPROVE after remaining slices.

**Reasoning:** Diff matches the brief’s safe-reuse intent, preserves numerical methodology, proves no stale scalar market state on the full-reval path, and updates FINDINGS/milestone/report as required. Remaining gaps are coverage/consistency polish, not blocking defects.
