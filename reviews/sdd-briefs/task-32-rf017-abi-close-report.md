# Task 32 Report — RF-017 ABI close as MET (no C++ VaR expansion)

## Task
RF-017 ABI close as MET (no C++ VaR expansion)

## Owner
C++ Performance Engineer (`docs/agents/06_CPP_PERFORMANCE_ENGINEER.md`)

## Status
**CLOSED** as **MET** for ABI. Named residual: product Historical VaR stays python/NumPy **by design**. Not ACCEPTED / DEFERRED. Milestone R0 leftover wave stays **IN PROGRESS** (not restored COMPLETE).

## Summary
Verified on disk (BASE `90e40a2`): ABI version, status/error return, length validation, contiguous `pnl_from_arrays`, and serial-below-4096. QA-025 caller-length mismatch is already pinned in `kernel_test.cpp` and the Python ctypes wrapper (`test_native_length_mismatch_fails_closed`); no hole, so no new wrapper pin. Default `RISKFORGE_SCENARIO_KERNEL=python` is the Decision (“do not move VaR into C++”), not an open ABI gap. No QuantLib or VaR kernels added in C++. FINDINGS RF-017 **CLOSED** as MET; `OPEN_LEFTOVERS` dropped RF-017.

## Files changed
- `backend/tests/test_rf020_r0_exit.py` — drop RF-017 from `OPEN_LEFTOVERS`; CLOSED-as-MET pin (TDD: failed first)
- `reviews/FINDINGS.md` — RF-017 **CLOSED** as MET; named residual python/NumPy by design
- `reviews/REMEDIATION_MILESTONE.md` — R0.12.9 close-gate record
- `ROADMAP.md` — leftover-wave gate drops RF-017 from open list
- `docs/known_limitations.md` — ABI MET; residual by design
- `reviews/r0.12.9-rf017-abi-close-report.md` — scoring report
- `reviews/sdd-briefs/task-32-rf017-abi-close-report.md` — this handoff

## Public/interface changes
- None. C ABI, ctypes wrapper, and Historical VaR default backend unchanged.

## Numerical conventions
- Units: currency P&L on the Exposure/Shock ABI (unchanged)
- Sign convention: unchanged
- Day count/calendar if relevant: n/a
- Tolerances/reference: `KERNEL_ABI_*` = 1e-12 (Python ↔ native ↔ C++ serial/parallel)

## Tests added/updated
- `test_rf017_closed_as_met_abi_not_accepted_deferred` — FINDINGS RF-017 CLOSED, MET, by-design residual; not IN PROGRESS / ACCEPTED / DEFERRED
- `OPEN_LEFTOVERS` no longer includes RF-017
- Existing native ABI / contiguous / serial-below-4096 pins re-run (no new wrapper mismatch pin; QA-025 already present)

TDD: close-gate test failed first (`Status: **CLOSED**` missing). After FINDINGS, GREEN.

## Commands executed
```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_rf020_r0_exit.py
# RED: 1 failed, 5 passed (FINDINGS still IN PROGRESS)

PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_rf020_r0_exit.py tests/test_native_kernel.py
# GREEN: 28 passed in 23.10s

.venv/bin/ruff check tests/test_rf020_r0_exit.py
# All checks passed
```

## Results
- Backend required suite: **28 passed** in 23.10s (`test_rf020_r0_exit.py` + `test_native_kernel.py`)
- Ruff: all checks passed
- Frontend: n/a
- QuantLib: not added to C++; not exercised numerically this slice
- C++: no new kernels; existing `kernel_test.cpp` / ctypes ABI tests in the native pytest module
- Build: n/a
- All tests pass (all applicable/affected suites required by the task): **yes**
- Unexplained failures or skips: none
- CI is green (all required checks): not started (commit this slice; no push unless requested)

## MET vs PARTIAL vs UNMET (this gate)

| Cell | Score | Evidence |
|---|---|---|
| ABI version | **MET** | `RISKFORGE_KERNEL_ABI` / `riskforge_kernel_abi_version` / `KERNEL_ABI_VERSION` |
| Status/error return | **MET** | `KERNEL_OK` / `KERNEL_ERR_*` |
| Length validation | **MET** | fail-closed before buffer walk; wrap/tight-buffer pins |
| QA-025 mismatch | **MET** | `kernel_test.cpp` + Python `test_native_length_mismatch_fails_closed` |
| Contiguous `pnl_from_arrays` | **MET** | C-contiguous float64 pointers; Fortran copies |
| Serial-below-4096 | **MET** | `KERNEL_PARALLEL_MIN_WORK == 4096` |
| Product Historical VaR python/NumPy | **by design** | Decision; not an ABI hole |
| C++ VaR / QuantLib kernels | **out of scope** | not added |

## Why CLOSE (not KEEP OPEN)
Required direction is ABI/validation/contiguous buffers, not moving VaR into C++. Those ABI cells are on disk and tested. Keeping RF-017 open only because the default kernel is python/NumPy would treat the Decision as an ABI gap.

## Known limitations / risks
- Default Historical VaR remains python/NumPy by design
- Object `pnl()` still packs lists (reference ABI; native Historical uses `pnl_from_arrays`)
- Large E×S still creates stdlib threads per call above the 4096 threshold (no process-lifetime pool)
- SIMD / thread-pool reuse remains out of scope
- No C++ VaR or QuantLib kernels

## Follow-up / next owner
- Owner: independent reviewer (Task 32 review)
- Requested action: APPROVE CLOSE as MET; do not expand native VaR/QuantLib; do not restore Milestone R0 COMPLETE
- Blocking?: no
