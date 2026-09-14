# QuantLineage 10/10 Subagent Rules

Lead Architect owns sequencing. Each implementer owns one task. Do not dual-own the same files in parallel.

## Product rules

- QuantLib prices. QuantLineage manages portfolio risk.
- LLM orchestrates deterministic tools. It never calculates financial risk.
- Correctness before performance.
- `MarketSnapshot` is authoritative market state.
- RiskRun identity is reproducible.
- No fake production claims.
- No frontend risk math.
- C++ only for measured numerical kernels.
- No unrelated infrastructure rewrites.
- Do not reopen Milestone R0 / RF-005 merely because Stage 10.x exists. R0 is COMPLETE. These stages are net-new portfolio upgrades.

## Quant contract (required in every quant change)

State explicitly:

- shock unit
- sensitivity unit
- sign convention
- currency / notional convention
- base market
- reconciliation expectation

Tests must catch: DV01×100, vega÷100, relative-vol confusion, reversed FX, wrong tail, dropped factor/trade/scenario, wrong as_of, wrong dataset/snapshot lineage, parallel DV01 used as key-rate DV01.

## Benchmark contract

measure → bottleneck → change → benchmark → parity

Never switch methodology to make timings look better.

## Documentation contract

Always distinguish: demo vs observed data; approximate vs exact; benchmark vs SLA; scoped pricing vs production coverage; portfolio project vs production platform.

## Workflow

1. Read the task brief first. It is the requirements source.
2. Inspect current code. Do not assume the brief is newer than the repo.
3. Implement the smallest coherent change.
4. Add regression / golden tests with the behavior change.
5. Run focused tests, then the affected suite.
6. Commit on the feature branch with the date the Lead specified.
7. Write the report file. Return only status, commits, one-line test summary, concerns.

## Do not

- Invent risk numbers in docs, UI, or AI text.
- Broadcast one equity/vol/rate/FX series onto every name or tenor on the Stage 10.1 dataset.
- Treat four-macro fixtures as the production demo after 10.1 lands.
- Claim FULL_REVALUATION SLAs.
- Add products or infrastructure for breadth after 10.6.
