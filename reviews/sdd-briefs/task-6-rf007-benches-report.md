# Task 6 Report — RF-007 acceptance benches

## Task
R0.6.7 — Record FINDINGS RF-007 acceptance benches without inventing SLAs.

## Owner
QA & Quant Validation Engineer

## Status
**DONE_WITH_CONCERNS**

## Summary
Extended `benchmarks/run_full_reval_bench.py --json` so the payload still emits the R0.6.1 1×120 builtin identity (`checksum` `6602fa6906f2579f5c89af72a41ab274c07650234fff69387bc2202b5a40534f`) and adds a PR-safe **10×50** `acceptance` object: `wall_ms` / `wall_ms_cold` / `wall_ms_warm`, `peak_rss_kib`, `scenarios_per_sec`, builtin vs QuantLib at the same N×S (skip-or-run / `QUANTLINEAGE_REQUIRE_QUANTLIB=1` fail-closed). Pytest asserts those values are finite, **not** floors. No `throughput` key. `check_m6_sla.py` is not invoked. RF-007 stays **IN PROGRESS**. Do not close.

## Files changed
- `benchmarks/run_full_reval_bench.py`
- `backend/tests/test_full_reval_bench.py`
- `benchmarks/README.md`
- `reviews/FINDINGS.md` — RF-007 residual still IN PROGRESS
- `reviews/REMEDIATION_MILESTONE.md` — § R0.6.7; close gate KEEP OPEN
- `reviews/r0.6.7-acceptance-benches-report.md`
- `reviews/sdd-briefs/task-6-rf007-benches-report.md` — this handoff (not in the implementation commit)

## Public/interface changes
- None (bench JSON payload only). Operator flags `--acceptance-n` / `--acceptance-s`; PR default 10×50.

## Numerical conventions
- Units: cash equity `quantity=10`, spot `100`; P&L = shocked PV − base PV ≡ `N * 10 * 100 * r`.
- Sign convention: down-move negative P&L.
- Tolerances/reference: allclose atol `1e-12`; R0.6.1 checksum unchanged; 10×50 engine digest `a28cf4ee6199bf40da3f2598f4241fc85fa4adc4f86bccbbd97e4938047d7537`.
- `wall_ms` / RSS / scenarios/sec: recorded only, not SLA.

## Tests added/updated
- `test_full_reval_bench_emits_identity_json` — 1×120 pin; `wall_ms` finite
- `test_full_reval_bench_script_is_identity_not_sla` — no SLA floors / no `check_m6_sla`
- `test_full_reval_bench_acceptance_records_matrix_without_sla` — 10×50 recorded fields
- `test_full_reval_bench_quantlib_same_nxs` — hard-gate skip-or-run; same N×S + checksum

## Commands executed
```bash
cd /Users/user/src/quantlineage/backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short tests/test_full_reval_bench.py
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
  tests/test_full_reval_bench.py \
  tests/test_full_reval_golden.py \
  tests/test_r065_process_partition.py::test_r061_checksum_is_identity_scaling_evidence_not_sla
.venv/bin/python -m ruff check tests/test_full_reval_bench.py ../benchmarks/run_full_reval_bench.py
cd /Users/user/src/quantlineage && /usr/bin/git diff --check
```

RED (tests before harness): 3 failed (`KeyError: acceptance` / missing 10×50 checksum in source), 1 passed.

## Results
- Focused bench tests: **4 passed** in 2.95s
- Identity goldens + R0.6.1 checksum pin: **9 passed** in 3.79s (1 pre-existing Starlette `TestClient` deprecation warning from the r065 import)
- Ruff: all checks passed
- `git diff --check`: passed
- Frontend: n/a
- QuantLib: available locally (1.43); 10×50 QuantLib row recorded; skip-or-run if missing
- C++: unchanged
- All applicable/affected suites required by the task: yes
- Unexplained failures or skips: none
- CI is green: not started from this slice

## MET vs UNMET matrix (FINDINGS RF-007 acceptance evidence)

| Cell | Score | Notes |
|---|---|---|
| N trades × S scenarios | **PARTIAL** | 10×50 + 1×120 identity; N=100/1k **UNMET** in default PR |
| wall time | **MET** at 10×50 | finite `wall_ms` / cold / warm; no floor |
| peak RSS | **PARTIAL** | field exists; process-lifetime `ru_maxrss`; QuantLib includes prior builtin |
| scenarios/sec | **MET** at 10×50 | recorded only; no `throughput` gate |
| builtin vs QuantLib | **PARTIAL** | same N×S skip-or-run; cash equity is `quantity * spot`, not reconstruction |
| warm vs cold | **MET** at 10×50 | two `wall_ms` on the same fixture |
| identical numerical results | **MET** | R0.6.1 `6602fa69…`; 10×50 `a28cf4ee…`; goldens 4 passed |

**Still UNMET for P0 close sizes:** N=100 / 1k and S=750 / 1k in the default PR test (CLI only; brief forbade 1k in PR).

RF-007 remains **IN PROGRESS**. Option A intra-run scenario-block multiprocessing remains PARTIAL.

## Self-review
- R0.6.1 identity checksum unchanged; no SLA floors; no C++ expansion; no RF-007 close; no nightly/PR-FULL job.
- QuantLib skip cannot hide missing builtin fields; dedicated QL test uses `import_quantlib()`.
- Close scores: peak RSS and builtin vs QuantLib are **PARTIAL**, not MET. Cash-equity QuantLib path is `quantity * spot` (same formula as builtin), not a curve/option rebuild. Peak RSS is process-lifetime `ru_maxrss`.

## Known limitations / risks
- N=100/1k **UNMET** in PR default (intentional).
- Builtin vs QuantLib **PARTIAL**: cash-equity QuantLib is `quantity * spot`, not reconstruction.
- Peak RSS **PARTIAL**: process-lifetime `ru_maxrss`; QuantLib figure includes prior builtin.
- Option A remains PARTIAL.
- RF-007 stays **IN PROGRESS**, not closed.

## Follow-up / next owner
- Owner: Lead Architect / Task 7 close re-gate
- Requested action: keep RF-007 IN PROGRESS; do not invent SLA from recorded numbers
- Blocking?: yes for RF-007 close

## Return line
DONE_WITH_CONCERNS | `c12de23` | 4 passed (bench) / 9 passed with goldens+checksum pin | N×S **PARTIAL**; wall **MET** at 10×50; peak RSS **PARTIAL**; scenarios/sec **MET** at 10×50; builtin vs QuantLib **PARTIAL**; warm vs cold **MET** at 10×50; identity **MET**; N=100/1k **UNMET** | cash-equity QL; cumulative `ru_maxrss`; no SLA; RF-007 **IN PROGRESS**

## Scoring fix (2026-09-09)

Independent review (Important): FINDINGS and milestone must not score QuantLib or peak RSS as **MET**. Restated close bar: N×S **PARTIAL** (10×50 + 1×120; N=100/1k **UNMET** in default PR); wall **MET** at 10×50; peak RSS **PARTIAL** (field exists; process-lifetime `ru_maxrss`; QuantLib includes prior builtin); scenarios/sec **MET** at 10×50; builtin vs QuantLib **PARTIAL** (same N×S, cash equity is `quantity * spot`, not reconstruction); warm vs cold **MET** at 10×50; identity **MET**; N=100/1k still **UNMET**. RF-007 stays **IN PROGRESS**. Docs-only follow-up commit; do not amend `c12de23`.
