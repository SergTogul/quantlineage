# QuantLineage Wave C Cursor Orchestrator

Read all Wave C files and inspect existing deterministic risk-query/tool code before changing anything.

Mission:
make QuantLineage AI-native through typed deterministic tools and MCP while preserving:
**The model orchestrates; QuantLineage calculates.**

Hard rules:
- no LLM financial arithmetic
- no invented numbers
- explicit tool allowlist
- no shell/SQL/filesystem/general HTTP tool
- preserve provenance
- clarify ambiguity
- no trade execution or personalized investment advice
- core app works without AI/MCP

Execute:
G1 tool contracts
→ G2 MCP
→ G3 orchestration
→ G4 grounded explanations
→ G5 UI/devex
→ G6 evals/safety
→ G7 demo/hostile review

For each item:
inspect → mark IN_PROGRESS → narrow subagent → implement → tests/evals → independent review → fix confirmed findings → retest → evidence → DONE.

Mandatory hostile cases:
prompt injection, fake tool, wrong units, user-supplied fake VaR, stale/mismatched run IDs, missing data, secret request, auth bypass, tool loop, numeric answer without deterministic evidence.

Stop when G7 passes and CI is green.
