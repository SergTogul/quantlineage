# Goal: Hosted OpenAI Risk Assistant

## Objective

Ship an opt-in OpenAI-backed risk assistant in QuantLineage that understands natural-language questions, selects existing deterministic risk tools, and (after the first-release gate) can run a bounded multi-tool investigation with grounded narration — while preserving the current API, MCP boundary, numerical grounding, provenance, and deterministic fallback.

## First-release outcome

A developer can:

1. copy `.env.example` to `.env`;
2. set `OPENAI_API_KEY`;
3. set `AI_PROVIDER=openai` and a model;
4. start QuantLineage;
5. ask a supported question in the existing Risk Query UI;
6. see a response calculated and formatted by existing QuantLineage code.

The browser never receives or stores the key.

T00–T15 (one-tool router) are complete. That is not the full goal.

## Milestone 2 outcome

The assistant can investigate with more than one allowlisted tool in a single request:

1. OpenAI may request multiple validated tools across a bounded Responses loop (≤4 rounds);
2. QuantLineage executes each call through existing `TOOL_CONTRACTS` and `PortfolioService`;
3. narration may be used only when every numeric claim is present in (or deterministically formatted from) tool payloads;
4. otherwise the existing deterministic formatter remains authoritative.

## Definition of done

### First release (T00–T15) — complete

- [x] Deterministic routing remains the default.
- [x] Local `.env` loading works and does not override exported env vars.
- [x] The OpenAI Python SDK uses the Responses API.
- [x] OpenAI function tools are derived from existing `TOOL_CONTRACTS` in strict mode.
- [x] The provider implements the existing one-tool `RiskAssistantModel` seam.
- [x] Every returned tool name and argument set is validated again in the application.
- [x] Tool execution continues through `PortfolioService`.
- [x] Numerical answers use existing deterministic formatters.
- [x] Transient provider failures fall back safely before tool execution.
- [x] No fallback replays a potentially side-effecting tool.
- [x] Existing HTTP request/response behavior remains compatible.
- [x] The UI shows provider/fallback status and has no key input.
- [x] Normal tests are network-free.
- [x] The routing/safety evaluation gate in the implementation plan passes.
- [x] Setup, rollback, and operating behavior are documented.
- [x] An opt-in live smoke test is available but excluded from normal CI.

### Milestone 2 (T20–T24) — OPEN

- [x] A higher-level `RiskAssistant` protocol exists; `RiskAssistantModel` remains a working one-tool adapter.
- [ ] A bounded Responses tool loop executes validated function calls for at most four rounds.
- [ ] Narration with unsupported numeric claims is rejected; deterministic formatting is the fallback.
- [ ] Multi-tool investigation evals cover comparisons, provenance, contributors, limits, and stress.
- [ ] A recorded decision exists on whether `price_instrument` / `calculate_greeks` / curve tools belong in `TOOL_CONTRACTS`.

**Do not mark this goal complete while T20–T24 remain open.** Deferred ≠ done.

## Non-negotiable constraints

1. The model orchestrates; QuantLineage calculates.
2. No API key in UI state, browser storage, client bundle, API payloads, logs, tool arguments, or MCP messages.
3. No arbitrary code, SQL, shell, filesystem, or unrestricted network tool.
4. No trading advice, order placement, or automatic portfolio mutation.
5. `backend/app/mcp.py` stays LLM-independent.
6. `TOOL_CONTRACTS` stays the canonical tool allowlist.
7. Invalid or unknown tool calls execute nothing.
8. Heavy RiskRuns are not automatically replayed or polled inside the assistant request.
9. The feature can be disabled with `AI_PROVIDER=deterministic`.
10. Multi-tool narration is in scope for T20–T24 (first-release evaluation gate has passed). It remains separately flagged, round-capped, and numerically grounded.

## Success measures

- Supported routing: at least 15 of 16 evaluation paraphrases select the expected tool or a safe clarification.
- Safety categories: 100% correct blocking/clarification.
- Executed tools: 100% allowlisted and schema-valid.
- Numeric grounding: 100% deterministic in the first release; milestone 2 narration is 100% payload-grounded or replaced by the deterministic formatter.
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

Work exactly one unchecked task from `TASKS.md` per iteration. Meet its acceptance criteria, run its checks, record evidence. T00–T15 being checked does **not** complete this goal. Continue with T20–T24. Do not stop after a “deferred remaining” note.
