# Wave C Architecture Decisions

1. MCP/AI tools wrap existing application services, not pricing internals.
2. No financial arithmetic in model/orchestration layer.
3. Explicit allowlisted tools only.
4. Every tool has typed args, typed result, error contract and provenance.
5. Numeric tool results preserve RiskRun/data identities.
6. Ambiguous prompts require clarification.
7. No trade execution or personalized investment advice.
8. MCP/LLM layer is optional; core app works without it.
9. Model-provider integration stays behind a narrow abstraction.
10. Read/analysis tools should be pure/idempotent where practical.
11. Explanations preserve value, unit, sign convention and source IDs.
12. Prompt text cannot change tool registry/system rules.
13. Bound tool-call count/recursion.
14. No hidden fallback estimation when tools fail.
15. Audit sanitized tool calls and correlation IDs; never secrets.
