# Task 3 Brief — R0.6.6 Contribution reuse

**Plan:** `reviews/sdd-briefs/r0-continuation-plan.md`  
**Owner agent:** Portfolio Risk Engineer — read `docs/agents/04_PORTFOLIO_RISK_ENGINEER.md`, `AGENTS.md`, `docs/agents/WORKFLOW.md`, `docs/agents/DEFINITION_OF_DONE.md`  
**Finding:** RF-007 — keep **IN PROGRESS** (do not CLOSED)  
**Milestone:** `reviews/REMEDIATION_MILESTONE.md` § R0.6.6  
**Workspace:** `/Users/user/src/riskforge-mvp` branch `r0-core-remediation`  
**BASE:** `68c302a` (Task 2 APPROVE)

## Goal

Avoid whole-book full revaluation **once per factor family** when the same trade/scenario P&Ls can be reused or decomposed coherently.

Today `_aggregate_factor_pnl_full_reval` (and panel variant) can apply family-only shocks and re-price the book per family × observation. Reuse trade/scenario grain (or decompose from already-computed shocked P&Ls) so contributions do not multiply N×S by number of families.

## Requirements

1. Full-reval factor contributions must not independently reprice the whole book once per factor family when existing trade/scenario P&Ls or isolated-shock artifacts can be reused.
2. Preserve contribution reconcile invariants (position/factor contributions reconcile to portfolio within existing tests/tolerances).
3. Do not invent risk numbers in tests; pin against existing goldens / `test_scenario_attribution.py` / ES contribution tests.
4. Call-count or equivalent proof: family contributions do not multiply `value`/`apply_scenario` by number of families beyond a documented bound (e.g. still O(S) applies, not O(families×S) extra full books — or document remaining necessary isolation revals).
5. Update FINDINGS RF-007 status line (still IN PROGRESS) and milestone § R0.6.6 COMPLETE pending review.
6. Write `reviews/r0.6.6-contribution-reuse-report.md`.
7. **Commit** one focused commit (`feat(r0.6): ...`).

## Out of scope

- Closing RF-007
- R0.6.5 process parallelism
- C++ kernels
- Changing R0.6.3/R0.6.4 unless a tiny caller wrap (e.g. `bypass_valuation_lru`) is required

## Suggested tests

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_es.py \
  tests/test_var.py \
  tests/test_scenario_attribution.py \
  tests/test_pricing_anti_cache.py
```
Plus new reuse/reconcile tests you add.

## Report contract

Write full report to: `reviews/sdd-briefs/task-3-r0.6.6-report.md`  
Return only: status (DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED), commit SHA(s), one-line test summary, concerns.
