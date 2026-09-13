# Wave C Tasks

## C1 Deterministic Tool Contracts
Minimum tools:
- search_instruments
- get_market_history
- get_data_quality
- run_portfolio_risk
- get_risk_run
- compare_risk_runs
- explain_risk_change
- run_stress
- get_key_rate_dv01
- get_top_risk_contributors
Optional: compare_hedge, get_run_provenance

Map every tool to an existing deterministic application service.
Use strict schemas/enums/date bounds and typed errors.

## C2 MCP Server
Implement a thin MCP server:
- allowlisted tool registration
- helpful methodology/unit descriptions
- reuse existing auth rules
- domain error mapping
- no quant formulas in MCP layer

Test tool discovery, valid calls, invalid args, unknown tools, auth, and operation without external LLM.

## C3 AI Orchestration
Intent taxonomy:
- instrument discovery
- history
- portfolio risk
- stress
- contributors
- run comparison
- risk-change explanation
- provenance

Ambiguity must clarify.
Model output cannot create arbitrary tool names.
Tool failure must not trigger estimated numbers.

## C4 Grounded Explanations
Risk answers should include:
- metric
- value
- unit
- sign convention
- run id
- as_of
- methodology
- dataset/snapshot identity

Risk-change explanation summarizes T0/T1, total change, trade/portfolio, market/factors, residual, top contributors, config changes—without recomputing.

## C5 UI / Developer Experience
Risk Query UI with contextual examples:
- Why did VaR change?
- Top contributors?
- Show USD 10Y KR-DV01.
- Run equity-down stress.
- Compare these RiskRuns.

Render structured result cards and provenance.
Create `docs/mcp.md` and a minimal client/config example.

## C6 Evals / Safety
Eval:
- missing data hallucination
- ambiguous portfolios/runs
- prompt injection
- fake/hidden tool request
- API-key request
- advisory/trading request
- misleading user-supplied numbers
- unit traps
- stale/mismatched run IDs
- malformed/oversized tool args

Expected: deterministic tool truth wins; unsupported paths fail/clarify.

## C7 Demo / Hostile Review
Demo:
search Apple → data quality → run risk → contributors → why VaR changed → stress → 10Y KR-DV01 → provenance → unsupported request.

Create `reviews/wave-c-ai-mcp-hostile-review.md`.

Attack:
tool injection, fake tool, wrong units, fake VaR in prompt, stale ids, missing data, auth bypass, secret exfiltration, infinite loop, numeric response without tool evidence.
