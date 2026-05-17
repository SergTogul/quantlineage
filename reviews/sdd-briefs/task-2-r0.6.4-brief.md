# Task 2 Brief — R0.6.4 Remove anti-cache behavior

**Plan:** `reviews/sdd-briefs/r0-continuation-plan.md`  
**Owner agent:** Quant Pricing Engineer — read `docs/agents/02_QUANT_PRICING_ENGINEER.md`, `AGENTS.md`, `docs/agents/WORKFLOW.md`, `docs/agents/DEFINITION_OF_DONE.md`  
Coordinate with Portfolio Risk **only** if `HistoricalRiskEngine` / risk-layer cache must change. Prefer pricing-layer `CachedPricingEngine` / valuation LRU.  
**Finding:** RF-007 — keep **IN PROGRESS** (do not CLOSED)  
**Milestone:** `reviews/REMEDIATION_MILESTONE.md` § R0.6.4  
**Workspace:** `/Users/user/src/riskforge-mvp` branch `r0-core-remediation`  
**BASE:** `35bf9fa` (Task 1 APPROVE)

## Goal

If the valuation LRU is slower for unique shocked markets, **disable it for that execution class** or redesign the caching level.

Typical problem: generic pricing LRU keyed by snapshot has near-zero hit rate on unique shocked snapshots and adds lookup/copy cost.

## Requirements

1. Identify the valuation LRU / `CachedPricingEngine` (and any similar cache) used on full-reval / unique-shock paths.
2. For unique-shock / FULL_REVALUATION execution: bypass or disable the LRU (or cache at a level that actually hits — e.g. not per unique snapshot identity if that never repeats).
3. Do **not** cache stale market state (consistent with R0.6.3).
4. Numerical identity vs existing goldens / cold path (same tolerances as existing tests).
5. Test that unique-shock full-reval does not populate or consult a per-snapshot LRU in a way that can only miss (spy cache get/put counts, or document bypass with a test that the bypass path is taken).
6. Update FINDINGS RF-007 status line (still IN PROGRESS) and milestone § R0.6.4 COMPLETE pending review.
7. Write `reviews/r0.6.4-anti-cache-report.md`.
8. **Commit** one focused commit (`feat(r0.6): ...`).

## Out of scope

- Closing RF-007
- C++ kernels
- R0.6.5 process parallelism / R0.6.6 contribution reuse
- Changing QuantLib reuse from Task 1 unless required to wire bypass

## Suggested tests

```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_full_reval_bench.py \
  tests/test_quantlib_reuse.py \
  tests/test_pricing*.py \
  tests/test_cache*.py
```
Plus any new anti-cache tests. Focused suite green before commit.

## Report contract

Write full report to: `reviews/sdd-briefs/task-2-r0.6.4-report.md`  
Return only: status (DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED), commit SHA(s), one-line test summary, concerns.
