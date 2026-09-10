# Task 28 Brief — QA-024 QuantLib demo-artifact range

**Owner:** QA (`docs/agents/10_QA_QUANT_VALIDATION_ENGINEER.md`)  
**Finding:** QA-024 / RF-016 leftover — **MET only with a real range gate**, not byte-equality of builtin artifact.  
**BASE:** HEAD on `r0-core-remediation`

## Required

1. Nightly (or skip-unless-QuantLib) test: price/summarize the demo books with **QuantLib**, compare key numbers (`var_99`, `market_value`, named stress P&Ls) to `data/demo_risk_artifact.json` **bands**. Not bit-identical (swaps/QL vs builtin). Document the band (e.g. relative 25% or artifact-derived min/max already in `docs/demo/final_demo.md`).
2. Wire into nightly QuantLib job if a pytest file is the gate; do **not** add SLA floors; do **not** run `check_m6_sla.py` on ubuntu-latest.
3. TDD. FINDINGS: QA-024 **MET** on RF-016 status (remove leftover wording). Do not claim labeled-runner SLA MET.
4. Report `reviews/r0.12.8-qa024-ql-range-report.md`. Commit.
5. Tests: new range pins + existing `test_rf016_close_gate.py` updated so they no longer require “QA-024 leftover”.

## Report
`reviews/sdd-briefs/task-28-qa024-ql-range-report.md`
