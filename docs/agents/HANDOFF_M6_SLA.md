# Handoff: M6 SLA disposition (accepted PARTIAL)

## Task
Milestone 6 product VaR / risk-path wall-time SLA disposition

## Owner
Lead Architect / Orchestrator (C++ Performance — evidence references only)

## Summary
Closed the open **M6 SLA** residual with **Option B**: explicitly accept that there is **no product VaR / end-to-end risk-path wall-time SLA**, and keep Milestone 6 **PARTIAL**. M6.1–M6.7 engineering work remains DONE. Did **not** invent COMPLETE from microbenchmark tables. Did **not** start M11/M12.

Evidence basis (reference only): `benchmarks/RESULTS.md` (M6.2 / M6.4) documents developer-laptop kernel microbenches with host/workload caveats and repeatedly states they are **not** production SLAs or Historical VaR wall-time claims. Risk-path native opt-in + parity (M6.3–M6.7) prove correctness, not product latency.

## Files changed
- `ROADMAP.md` — Progress table, highest-risk gaps, suite row, M6 Formal SLA disposition + progress update
- `docs/agents/HANDOFF_M6_SLA.md` — this handoff
- `docs/agents/HANDOFF_LEFTOVERS.md` — M6 SLA row marked disposed (inventory sync)

## Public/interface changes
- None (documentation / roadmap status only)

## Numerical conventions
- N/A — no new SLA numbers invented
- Existing microbench / parity tolerances unchanged (`benchmarks/RESULTS.md`; `KERNEL_PNL_*`)

## Tests added/updated
- None (docs-only disposition)

## Commands executed
```bash
# Evidence read (no re-bench required for Option B)
# - ROADMAP.md Milestone 6 Progress + Formal SLA disposition
# - benchmarks/RESULTS.md (M6.2 / M6.4 caveats)
git status
git diff --stat
git log -5 --oneline
```

## Results
- Backend: n/a (docs only)
- Frontend: n/a
- QuantLib: n/a
- C++: n/a (RESULTS.md consulted only)
- Build: n/a

## Known limitations / risks
- Milestone 6 stays **PARTIAL** indefinitely until a product owner defines a measurable wall-time/throughput SLA with host/workload/method.
- Citing `benchmarks/RESULTS.md` speedups as capacity or VaR latency guarantees remains incorrect.
- Parallel M5.5 / M1.12 code work was intentionally not touched.

## Follow-up / next owner
- Owner: Product / Lead Architect (only if/when an SLA is desired)
- Requested action: If COMPLETE is needed later, publish a concrete risk-path SLA + measurement plan; C++ Performance may then collect evidence. Otherwise leave M6 PARTIAL.
- Blocking?: no — accepted residual; other residuals (M1.9+, M4.7 polish, M13, etc.) may proceed without inventing M6 COMPLETE
- Do not start: Milestone 11, Milestone 12 (POSTPONED)
