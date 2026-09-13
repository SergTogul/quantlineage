# QuantLineage Wave B Cursor Orchestrator

Read all Wave B files and inspect the current repo before coding.

Mission:
- historical analytics
- benchmark comparison
- institutional risk visualizations
- flagship risk-change waterfall

Hard rules:
- backend owns financial math
- frontend only requests/formats/charts
- preserve frozen data/run lineage
- reuse existing risk services
- no retail planner/optimizer scope

Execute:
G1 Historical analytics
→ G2 Benchmark
→ G3 Risk visuals
→ G4 Risk-change waterfall
→ G5 UI
→ G6 Demo
→ G7 Hostile review

For every item:
inspect → mark IN_PROGRESS → narrow subagent → implement smallest coherent change → tests → independent review → fix confirmed issues → rerun → record evidence → DONE.

Mandatory attacks:
percent/fraction, annualization, drawdown sign, tracking error, P&L/loss, bp/currency, benchmark date mismatch, hidden residual, stale UI response, frontend recomputation.

Stop when G7 passes and CI is green.
