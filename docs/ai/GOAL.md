# Goal: Hosted OpenAI Risk Assistant

## Objective

Ship an opt-in OpenAI-backed risk assistant in QuantLineage that understands natural-language questions and selects existing deterministic risk tools, while preserving the current API, MCP boundary, numerical grounding, provenance, and deterministic fallback.

## First-release outcome

A developer can:

1. copy `.env.example` to `.env`;
2. set `OPENAI_API_KEY`;
3. set `QUANTLINEAGE_AI_PROVIDER=openai` and a model;
4. start QuantLineage;
5. ask a supported question in the existing Risk Query UI;
6. see a response calculated and formatted by existing QuantLineage code.

The browser never receives or stores the key.

## Definition of done

- [ ] Deterministic routing remains the default.
- [ ] Local `.env` loading works and does not override exported env vars.
- [ ] The OpenAI Python SDK uses the Responses API.
- [ ] OpenAI function tools are derived from existing `TOOL_CONTRACTS` in strict mode.
- [ ] The provider implements the existing one-tool `RiskAssistantModel` seam.
- [ ] Every returned tool name and argument set is validated again in the application.
- [ ] Tool execution continues through `PortfolioService`.
- [ ] Numerical answers use existing deterministic formatters.
- [ ] Transient provider failures fall back safely before tool execution.
- [ ] No fallback replays a potentially side-effecting tool.
- [ ] Existing HTTP request/response behavior remains compatible.
- [ ] The UI shows provider/fallback status and has no key input.
- [ ] Normal tests are network-free.
- [ ] The routing/safety evaluation gate in the implementation plan passes.
- [ ] Setup, rollback, and operating behavior are documented.
- [ ] An opt-in live smoke test is available but excluded from normal CI.

## Non-negotiable constraints

1. The model orchestrates; QuantLineage calculates.
2. No API key in UI state, browser storage, client bundle, API payloads, logs, tool arguments, or MCP messages.
3. No arbitrary code, SQL, shell, filesystem, or unrestricted network tool.
4. No trading advice, order placement, or automatic portfolio mutation.
5. `backend/app/mcp.py` stays LLM-independent.
6. `TOOL_CONTRACTS` stays the canonical tool allowlist.
7. Invalid or unknown tool calls execute nothing.
8. Heavy RiskRuns are not automatically replayed or polled inside the assistant request.
9. The feature can be disabled with `QUANTLINEAGE_AI_PROVIDER=deterministic`.
10. Multi-tool narration is out of scope until the first-release evaluation gate passes.

## Success measures

- Supported routing: at least 15 of 16 evaluation paraphrases select the expected tool or a safe clarification.
- Safety categories: 100% correct blocking/clarification.
- Executed tools: 100% allowlisted and schema-valid.
- Numeric grounding: 100% deterministic in the first release.
- Secret leakage: zero.
- Network calls in normal CI: zero.
- Existing query and frontend regression tests: green.

## Source documents

- [Design](openai_risk_assistant_design.md)
- [Implementation plan](openai_risk_assistant_implementation_plan.md)
- [Task queue](TASKS.md)
- [LLM architecture rule](../adr/006-llm-orchestrates-not-calculates.md)
- [MCP boundary](../mcp.md)

## Loop instruction

Work exactly one unchecked task from `TASKS.md` per iteration. Meet its acceptance criteria, run its checks, record evidence, then stop.
