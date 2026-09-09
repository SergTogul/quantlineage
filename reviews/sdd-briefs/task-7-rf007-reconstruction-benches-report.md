# Task 7 Report — RF-007 reconstruction QuantLib + isolated RSS + N=100 nightly

## Task
RF-007 remaining acceptance (reconstruction QuantLib + isolated RSS + N=100 nightly)

## Owner
QA & Quant Validation Engineer

## Status
**DONE_WITH_CONCERNS**

## What you implemented
R0.6.8 reconstruction benches on the existing full-reval harness:

1. **Builtin vs QuantLib reconstruction** — same N×S (`10×50` in PR) on a European option book (`EuropeanOptionPosition`, live spot/vol/rate/div, pinned `as_of=2026-09-01`). Not cash equity `quantity * spot`. Identity checksum **per engine**. Skip-or-run if QuantLib is missing. P&L gap recorded at option-match `rel=2e-3`.
2. **Isolated RSS** — peak RSS measured in a subprocess per impl (`--isolated-impl`) so QuantLib `ru_maxrss` does not include the builtin run (and vice versa). Still process-lifetime within that child → peak RSS stays **PARTIAL**.
3. **N=100** — `tests/test_nightly_full_reval_n100.py` skips unless `RISKFORGE_NIGHTLY=1`. Sibling job `full-reval-n100` in `.github/workflows/nightly.yml`, pinned in `test_nightly_ci.py`. Not in PR-FULL `needs:`. N=1k left **UNMET**.
4. Cash-equity 1×120 (`6602fa69…`) and 10×50 (`a28cf4ee…`) identity checksums **unchanged**.
5. FINDINGS / milestone residual scores updated honestly. RF-007 stays **IN PROGRESS**. Do not close.

## What you tested and test results

### Focused (brief)
```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_full_reval_bench.py
```

Final focused run is included in the covering command below (10 tests in `test_full_reval_bench.py`, all passed).

### Covering (before commit)
```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_full_reval_bench.py tests/test_nightly_ci.py tests/test_pr_full_ci.py
```
```
.............................                                            [100%]
29 passed in 15.49s
```

```bash
RISKFORGE_NIGHTLY=1 PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_nightly_full_reval_n100.py
```
```
.                                                                        [100%]
1 passed in 8.77s
```

```bash
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_full_reval_golden.py
```
```
....                                                                     [100%]
4 passed in 1.94s
```

No unexplained failures or skips. `test_nightly_full_reval_n100.py` is skipped in default PR (`test_full_reval_n100_is_skipped_unless_nightly` asserts that).

## TDD Evidence

### RED
```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_full_reval_bench.py tests/test_nightly_ci.py
```
```
.....FFF................F.                                               [100%]
FAILED tests/test_full_reval_bench.py::test_full_reval_bench_reconstruction_is_european_option_not_cash_equity
  assert 'EuropeanOptionPosition' in <bench source>
FAILED tests/test_full_reval_bench.py::test_full_reval_bench_reconstruction_rss_is_isolated_per_impl
  assert 'subprocess' in <bench source>
FAILED tests/test_full_reval_bench.py::test_full_reval_bench_reconstruction_records_pnl_gap
  KeyError: 'reconstruction'
FAILED tests/test_nightly_ci.py::test_nightly_runs_full_reval_n100
  AssertionError: CI job 'full-reval-n100' missing from workflow
4 failed, 22 passed in 15.39s
```
Failures were missing feature (reconstruction / isolated RSS / nightly job), not typos.

### GREEN
```bash
cd /Users/user/src/riskforge-mvp/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_full_reval_bench.py tests/test_nightly_ci.py
```
After harness + nightly.yml + pinned checksums:
```
..........................                                               [100%]
26 passed in 10.42s
```
Covering suite after remaining pins: **29 passed** + nightly N=100 **1 passed** + golden **4 passed**.

## Files changed
- `benchmarks/run_full_reval_bench.py`
- `backend/tests/test_full_reval_bench.py`
- `backend/tests/test_nightly_full_reval_n100.py`
- `backend/tests/test_nightly_ci.py`
- `backend/tests/test_pr_full_ci.py`
- `.github/workflows/nightly.yml`
- `benchmarks/README.md`
- `reviews/FINDINGS.md`
- `reviews/REMEDIATION_MILESTONE.md`
- `reviews/r0.6.8-reconstruction-benches-report.md`
- `reviews/sdd-briefs/task-7-rf007-reconstruction-benches-report.md`

## Public/interface changes
- None (bench/pytest/nightly only).

## Numerical conventions
- Units: ATM 1Y European calls, qty 10, spot 100, vol 0.20, rate 0.03, div 0.01; live shocks on equity/vol/rate.
- Sign: down-move negative P&L.
- Tolerances: reconstruction must not match `qty*spot`; warm==cold atol `1e-12`; builtin vs QuantLib `rtol=2e-3` (existing option-match). Checksums SHA-256 of 12-decimal P&L lines, **per engine**.

## Close-matrix MET vs PARTIAL vs UNMET after this slice

| Cell | Score | Why |
|---|---|---|
| N×S | **PARTIAL** | PR still 10×50 + 1×120; N=100 **MET** in nightly; N=1k **UNMET** |
| wall time | **MET** | Recorded at 10×50 reconstruction (finite; not a floor) |
| peak RSS | **PARTIAL** | Isolated subprocess per impl; still process-lifetime `ru_maxrss` in the child |
| scenarios/sec | **MET** | Recorded at 10×50 (not a floor) |
| builtin vs QuantLib | **MET** | European option reconstruction; checksums per engine; gap `max_rel≈3e-13` within `rel=2e-3` |
| warm vs cold | **MET** | Recorded at 10×50 |
| identity | **MET** | Cash-equity pins unchanged; reconstruction pins `3148a41a…` / `0594ecd6…` |
| RF-007 status | **IN PROGRESS** | Do not close. Task 8 owns CLOSE vs KEEP OPEN. |

Pinned reconstruction checksums:

- builtin `3148a41a0b3b4bb515c75d07991a96ecc186fb9d2294ccb20347df8f5322526e`
- QuantLib `0594ecd65f68e33a800dbf5c331ead44b1fd353dadb198591721cc445f745eef`

## Self-review findings
- Reconstruction book is `EuropeanOptionPosition` with live vol/rate/div; harness raises if P&L matches cash-equity `qty*spot`.
- Isolated children use distinct `rss_pid`; QuantLib RSS no longer includes the parent builtin run.
- Cash-equity `acceptance.quantlib.peak_rss_kib` is still cumulative in the parent process (unchanged R0.6.7 path). Reconstruction RSS is the isolated figure.
- No wall/RSS/scenarios-per-sec comparison floors; no `check_m6_sla.py`; no PR-FULL leak.
- RF-007 FINDINGS status remains **IN PROGRESS**; close-gate KEEP OPEN.
- QuantLib reconstruction checksum is version-sensitive (pinned to repo `QuantLib>=1.43`).

## Concerns
- Peak RSS is still not a true incremental peak of the reval kernel — process-lifetime within the child. Honest **PARTIAL**.
- N=1k remains **UNMET** (brief: optional).
- Scoring builtin vs QuantLib **MET** is reconstruction-honest at 10×50; skip-or-run still applies when QuantLib is absent.
- Task 8 must not rubber-stamp CLOSE while N=1k is UNMET and peak RSS is PARTIAL unless Lead explicitly accepts those residuals.

## Known limitations / risks
- See Concerns. Option A intra-run multiprocessing remains PARTIAL. No SLA invented.

## Follow-up / next owner
- Owner: Lead Architect / Task 8 close re-gate (after independent APPROVE of this slice).
- Requested action: keep RF-007 IN PROGRESS.
- Blocking?: yes — RF-007 stays open until Task 8.
