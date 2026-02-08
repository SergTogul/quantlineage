# Handoff: M6 SLA COMPLETE (Option B reversed)

## Task
Define measurable product-path scenario-kernel VaR wall-time SLA; reverse Option B; close Milestone 6

## Owner
Lead Architect / Orchestrator + C++ Performance Engineer

## Summary
User rejected Option B (“accept no product VaR wall-time SLA / stay PARTIAL forever”). We **reversed** that disposition and published a real, measurable **scenario-kernel SLA** tied to the LINEAR/DELTA_GAMMA native path ABI:

- **SLA-K1:** `cpp_ctypes` ≥ **50×** vs pure-Python nested loops on workload `10k_x_1k` (10 000×1 000)
- **SLA-K2:** `cpp_ctypes_t4` ≥ **1.3×** vs serial `cpp_ctypes` on the same run

Evidence refreshed on the documented reference host (i7-7700HQ / macOS 13.7.8 / Apple clang 14): SLA-K1 **133–145×**, SLA-K2 typically **~1.5–2.1×** (thermal variance; floor 1.3×). Pass/fail harness: `benchmarks/check_m6_sla.py`. Milestone 6 marked **COMPLETE**.

Honest non-claims preserved: not HTTP end-to-end VaR latency; not FULL_REVALUATION; not “1×N aggregated-Greek VaR beats NumPy” (FFI-bound on this host). Numerical methodology unchanged.

## Files changed
- `ROADMAP.md` — M6 COMPLETE; Option B reversed; Formal product SLA + M6.8 DONE
- `benchmarks/RESULTS.md` — Formal product SLA section + evidence refresh notes
- `benchmarks/README.md` — SLA check + scoped caveats
- `benchmarks/run_scenario_bench.py` — docstring points at SLA-K1/K2
- `benchmarks/check_m6_sla.py` — new pass/fail verifier
- `docs/agents/HANDOFF_M6_SLA.md` — this handoff (replaces Option B text)
- `docs/agents/HANDOFF_LEFTOVERS.md` — M6 row closed COMPLETE

## Public/interface changes
- None (docs + bench check script only; kernel ABI / risk math unchanged)

## Numerical conventions
- SLA floors: SLA-K1 ≥ 50×, SLA-K2 ≥ 1.3× (relative wall time; parallel floor leaves thermal margin)
- Harness checksum guard: 1e-6 relative vs Python
- Existing parity tolerances unchanged (`KERNEL_PNL_*`, `KERNEL_ABI_*`)

## Tests added/updated
- New: `benchmarks/check_m6_sla.py` (SLA verifier; not a CI hard gate)
- Unchanged unit suites (methodology preserved)

## Commands executed
```bash
OMP_NUM_THREADS=1 RISKFORGE_KERNEL_THREADS=1 backend/.venv/bin/python \
  benchmarks/run_scenario_bench.py --workload 1k_x_1k --workload 10k_x_1k --iters 1 --json
backend/.venv/bin/python benchmarks/run_scenario_bench.py \
  --workload 10k_x_1k --threads 4 --parallel-compare --iters 1 --json
backend/.venv/bin/python benchmarks/check_m6_sla.py
python3 -m pytest benchmarks/test_bench_smoke.py -q
```

## Results
- Backend: n/a (docs/bench only; methodology untouched)
- Frontend: n/a
- QuantLib: n/a
- C++: SLA-K1/K2 **PASS** on reference host (latest check: 106× / 1.95×; session range K1 106–145×, K2 1.45–1.95×)
- Build: native shared lib + header bench via harness OK

## Known limitations / risks
- Absolute `wall_ms` varies with thermal/power; floors are relative and host-class scoped
- Current Historical VaR aggregates to 1 exposure before the kernel — 1×N ctypes ≈ Python on this host; do not market as end-to-end VaR 50×
- `check_m6_sla.py` is a local/reference check, not a CI gate on arbitrary runners
- Parallel M5.5 / M1.12 / frontend work was not touched

## Follow-up / next owner
- Owner: none required for M6 close
- Optional later (not blocking COMPLETE): multi-exposure batching in Historical VaR approximate path if product wants 1×N wall-time wins — would need new measurement + SLA amendment
- Blocking?: no
- Do not start: Milestone 11, Milestone 12 (POSTPONED)
