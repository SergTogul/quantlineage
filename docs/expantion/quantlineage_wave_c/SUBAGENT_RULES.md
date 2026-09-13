# Wave C Subagent Rules

Roles:
- Tool Contract Agent
- MCP Agent
- AI Orchestration Agent
- Quant Grounding Agent
- Security/Injection Agent
- Frontend AI UX Agent
- Eval Agent
- Independent Reviewer

Rules:
- no arbitrary tools outside allowlist
- no model-side financial arithmetic
- no general shell/SQL/filesystem/HTTP tools
- freeze tool contracts before UI/orchestration integration
- security reviewer reviews independently

Loop:
inspect → tracker IN_PROGRESS → narrow subagent → implement → tests/evals → independent review → fix → retest → evidence → DONE.
