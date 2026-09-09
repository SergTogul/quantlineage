# Task 3 Review — R0.6.6 Contribution reuse

**Base:** `68c302a`  
**Head:** `8afd4e4`  
**Diff reviewed:** `.superpowers/sdd/review-68c302a..8afd4e4.diff`  
**Brief:** `reviews/sdd-briefs/task-3-r0.6.6-brief.md`  
**Implementer report (unverified claims):** `reviews/sdd-briefs/task-3-r0.6.6-report.md`

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

Checked against the task brief and binding global constraints. Implementer report treated as unverified; evidence is the `68c302a..8afd4e4` diff.

| Requirement | Evidence in diff | Status |
|---|---|---|
| Full-reval factor contributions must not independently reprice the whole book once per factor family | `_aggregate_factor_pnl_full_reval` / `_from_panel` no longer loop families × observations through `apply_market_scenario` + `value_portfolio`. They call the existing Δ-Γ helpers and set `interaction = total − sum(families)`. Scenario `_factor_isolated_pnl` no longer builds isolated `Scenario` objects or calls `apply_scenario` per key | Met |
| Preserve contribution reconcile invariants | Residual still assigned to `interaction`; existing `test_es_contributions.py` / `test_scenario_attribution.py` still assert abs `1e-6` / rel `1e-8`; new reuse tests assert the same | Met |
| Do not invent risk numbers; pin against existing goldens / ES / scenario suites | Cash-equity FULL family series / factor ES pinned to LINEAR at abs `1e-12`; no new invented goldens; comment-only updates on existing convention headers | Met |
| Call-count or equivalent proof: not O(families×S) extra full books | `test_contribution_reuse.py`: helper `value` calls == N, `apply` lists empty; ES report `calls <= N×(S+3)` and `< N×(1+S×(1+F))`; scenario `apply_scenario` once, `value` == 2N | Met |
| FINDINGS RF-007 stays IN PROGRESS; milestone § R0.6.6 COMPLETE pending review | Status line still **IN PROGRESS** / “Do not close”; § R0.6.6 titled COMPLETE pending review | Met |
| Write `reviews/r0.6.6-contribution-reuse-report.md` | Added in the same commit, including the remaining-isolation-revals bound (**none** on this path) | Met |
| One focused commit (`feat(r0.6): ...`); no C++ / no RF-007 close | Single commit `8afd4e4 feat(r0.6): reuse joint P&L for factor contributions`; native kernels untouched | Met |
| Preserve interfaces; LLM does not invent numbers; no native kernel expansion | `ESContributionAnalytics.report` / `ScenarioAttributionEngine.decompose` signatures unchanged; no DTO/API change | Met |
| Behavior change has tests in the same change | New `backend/tests/test_contribution_reuse.py` (7 tests) in the owning commit | Met |
| Out of scope: no R0.6.5, no closing RF-007, no R0.6.3/R0.6.4 except tiny wrap | `bypass_valuation_lru` removed from the deleted isolated loops (correct: those unique snaps are gone). Joint full-reval bypass remains in `var.py` / `historical.py` | Met |

Intentional, documented convention change (brief-authorized, not a spec miss):

- Factor *bucket* amounts under FULL_REVAL / stress are now the additive Δ-Γ split of the joint P&L, not isolated-family full reval. Portfolio ES / trade P&L identity is unchanged. Nonlinear / unmapped remainder sits in `interaction`. Global constraint 2 is preserved for existing suites (they pin reconcile, not isolated-reval bucket goldens). Constraint 3 (do not change methodology solely for performance) is overridden by this task’s explicit reuse/decompose goal.

`tests/test_es.py` / `tests/test_var.py` from the brief do not exist; stand-ins in the report are reasonable. This review did not re-run the suite.

---

## Strengths

- Right performance model: family contributions cannot reuse isolated full-reval P&L without extra books, so attributing from one base Greek valuation and reconciling with the already-priced joint residual is the coherent decomposition the brief asked for.
- Call-count tests are structural, not wall-clock: they would fail if isolated `apply`/`value` came back, including the `hasattr` guard if `es.py` re-imported `apply_market_scenario`.
- Cash-equity identity is the correct numerical pin (linear instruments: isolated reval ≡ Greek split ≡ joint P&L; interaction ~ 0). Does not invent option-book goldens.
- Fail-closed panel coverage is preserved: the full-reval panel helper delegates to `_aggregate_factor_pnl_from_panel`, which still calls `require_panel_covers_portfolio`.
- Shock units on the scenario path go through existing helpers (`decimal_rate_to_bps`, `_panel_linear_contribution` / `relative_vol_move_to_vol_points`), not ad-hoc `* 100` / `/ 10000`.
- Process hygiene: RF-007 left open; milestone marked complete *pending review*; no C++ / no R0.6.5; ownership stays on `es.py` / `scenario_attribution.py`.

---

## Issues

### Critical (Must Fix)

None.

### Important (Should Fix)

None.

### Minor (Nice to Have)

1. **`interaction` is still labeled “Cross-factor interaction”**  
   - File: `backend/app/risk/scenario_attribution.py:49-50`, `backend/app/risk/es.py:52`  
   - After this change the bucket also holds single-factor convexity beyond Δ-Γ, option rate effects (no `dv01` / rates omitted from `required_factors_for_position`), and unmapped-instrument remainder. A single-factor option stress that previously had ~0 interaction can now show a large residual. `test_single_factor_interaction_near_zero` still only covers cash equity.  
   - Why it matters: UI/API consumers will read the leftover as cross-factor when it is a Taylor residual.  
   - Fix (optional): relabel to “unexplained / Taylor residual” (or similar) and/or add a one-line test that a single-factor option scenario leaves a non-trivial residual while still reconciling.

2. **Stale name `_factor_isolated_pnl`**  
   - File: `backend/app/risk/scenario_attribution.py:160`  
   - The function no longer isolates or reprices. Callers and future grep for “isolated” will think the extra books are still there.  
   - Fix: rename to `_factor_greek_pnl` / `_factor_attributed_pnl`.

3. **Scenario reuse tests do not pin bucket magnitudes**  
   - File: `backend/tests/test_contribution_reuse.py:233-293`  
   - New scenario tests assert apply-once, key set, and reconcile. A regression that zeroed every family bucket and dumped P&L into `interaction` would still pass those tests. ES cash-equity tests (`full["equity"] == total`) and existing `test_single_factor_interaction_near_zero` cover the linear book; the option/formal path has no equivalent magnitude pin.  
   - Fix: assert SPY (and SPY:VOL) buckets equal `_linear_shock_pnl` on the base valuations, with interaction = remainder.

4. **Product docs still describe isolated-reval factor ES; no ADR for the bucket convention**  
   - File: `ROADMAP.md` (FULL_REVALUATION: “factor-isolated reval + `interaction` residual”); no new file under `docs/adr/`  
   - Global constraint 2 allows a breaking convention with an ADR. Portfolio numbers did not break existing suites, but `by_risk_factor` on nonlinear books did change meaning.  
   - Fix: one sentence in ROADMAP (and optionally a short ADR) pointing at the R0.6.6 report. Not blocking for this gate.

---

## Recommendations

- Follow-up (not this slice): reuse the base `Valuation` objects already computed in `VaRAnalytics._full_reval_position_pnls` instead of a second O(N) `value` pass inside `_aggregate_factor_pnl_linear`. Bound is already O(N), not O(N×S×F).
- When RF-007 closes, state explicitly that contribution scaling is O(N×S) joint pricing plus O(N) Greeks, and that factor buckets under FULL_REVAL are Δ-Γ-plus-residual rather than isolated reval.

---

## Assessment

**Ready to merge?** Yes (task gate). Independent review APPROVE for R0.6.6; controller still owns RF-007 close.

**Reasoning:** The slice does what the brief asked: family contributions no longer multiply whole-book revals by F; reconcile and cash-equity identity hold; RF-007 stays open. Remaining notes are naming, label honesty, and test tightness — not missing scope or a correctness hole on the linear path the goldens actually pin.
