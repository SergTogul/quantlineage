# Task 7 Brief — RF-007 remaining acceptance (reconstruction QuantLib + N=100)

**Owner:** QA & Quant Validation (`docs/agents/10_QA_QUANT_VALIDATION_ENGINEER.md`) coordinating with Quant Pricing if a tiny option fixture is needed.  
**Finding:** RF-007 — keep **IN PROGRESS** until this slice is independently APPROVE **and** the close matrix is honestly MET/PARTIAL as below. Do not rubber-stamp CLOSE.  
**BASE:** `749e1e4` (leftover SDD briefs). Plan: `reviews/sdd-briefs/r0-continuation-plan.md`.

## Why this exists

The last close gate KEEP OPEN’d because:
- QuantLib path was cash equity (`quantity * spot`), not reconstruction
- peak RSS is process-lifetime `ru_maxrss` (QuantLib includes prior builtin)
- N=100 / 1k UNMET in default PR

## Required

1. **Builtin vs QuantLib reconstruction:** same N×S full-reval on a **European option** book (not cash equity `quantity * spot`). Fixture pattern: `EuropeanOptionPosition` like `backend/tests/test_quantlib_reuse.py` (spot/vol/rate/div live). Record wall_ms, scenarios/sec, identity checksum **per engine**. Skip-or-run if QuantLib missing (`tests.quantlib_gate`). Builtin vs QuantLib P&L need not share one SHA; record gap and use the existing option-match tolerance (`rel=2e-3` in `test_european_option_matches_builtin_closely`) or document a series-level tolerance. Pin each engine’s checksum.
2. **Isolated RSS:** measure peak RSS in a **subprocess per impl** so QuantLib `ru_maxrss` does not include the builtin run (and vice versa). Label honestly if still PARTIAL (process-lifetime within that child is OK).
3. **N=100:** record at least N=100 × modest S (e.g. 50) **outside default PR**. Pytest skip unless `RISKFORGE_NIGHTLY=1`; fail in nightly if missing. Add a sibling job in `.github/workflows/nightly.yml` and pin it in `backend/tests/test_nightly_ci.py` the same way as `hierarchy-benchmark` / `full-reval-sample`. N=1k optional same skip rule. No wall-time SLA floors. Do not add to PR-FULL `needs:`.
4. Keep R0.6.1 1×120 and R0.6.7 10×50 cash-equity identity tests unchanged (checksums `6602fa69…` / `a28cf4ee…`).
5. Update FINDINGS residual scores honestly. Still do **not** CLOSE RF-007. N=1k may stay UNMET.
6. Write `reviews/r0.6.8-reconstruction-benches-report.md`.
7. Follow TDD (failing tests first). **Commit** (`test(r0.6): ...`). Follow `docs/agents/HANDOFF_TEMPLATE.md` in the implementer report.

## Out of scope
- Fake SLAs
- C++ kernels
- Intra-run multiprocessing (Option A)

## Tests
```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_full_reval_bench.py
```

## Report
`reviews/sdd-briefs/task-7-rf007-reconstruction-benches-report.md`  
Return: status, SHA, MET vs UNMET, concerns.
