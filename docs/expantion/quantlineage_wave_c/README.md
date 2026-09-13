# QuantLineage Wave C — AI / MCP Deterministic Risk Interface

Goal: make QuantLineage AI-native without allowing an LLM to calculate financial risk.

Outcome:
- deterministic typed tools
- MCP server
- bounded AI orchestration
- grounded explanations
- Risk Query UI
- adversarial evals
- provenance on every numeric answer

Core rule: **the model orchestrates; QuantLineage calculates.**

The AI may choose tools, ask clarification, and summarize results.
It may not invent or calculate VaR/ES, stress, attribution, DV01, or other risk numbers.

Non-goals: autonomous trading, order execution, unrestricted shell/SQL/filesystem/HTTP tools, or mandatory external LLM dependency.

Developer entry for the optional MCP stdio server: [`docs/mcp.md`](../../mcp.md).
The Risk Query UI lives on Scenario Builder and Overview Command (`#overview/command`).
