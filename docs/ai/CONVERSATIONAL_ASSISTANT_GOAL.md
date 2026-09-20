# Goal: Grounded Conversational Risk Assistant

Status: Proposed corrective goal  
Target: PR #6 branch  
Source review: 2026-09-20

## Problem

The current OpenAI path behaves primarily as a one-shot intent router:

1. the UI sends a question to FastAPI;
2. OpenAI may select one tool;
3. QuantLineage executes the tool;
4. a deterministic formatter returns a predefined answer.

In addition, Greek questions are short-circuited before OpenAI is called. The API may still label those responses as `model-routed`.

This is safe, but it does not deliver the intended product: a conversational assistant that uses deterministic risk tools and explains their outputs.

## Objective

Convert Risk Query into a grounded conversational risk assistant:

```text
UI question
  -> backend assistant orchestrator
  -> OpenAI Responses API
  -> validated function call(s)
  -> shared QuantLineage tool executor
  -> QuantLib / deterministic risk services
  -> function_call_output returned to OpenAI
  -> grounded natural-language answer
  -> UI conversation
```

MCP remains an external protocol adapter over the same tool contracts. The in-process assistant uses the shared executor directly; it must not start an MCP subprocess or duplicate tool logic.

## First successful experience

With `AI_PROVIDER=openai`, a user asks:

> Which options have the largest delta, and why does that matter?

The model:

1. selects `get_position_greeks`;
2. supplies a typed option filter and `greek=delta`;
3. receives the deterministic result;
4. explains the ranking in natural language without inventing values;
5. preserves the structured tool result for the UI;
6. understands a follow-up such as “What about gamma?” in the same conversation.

## Definition of done

- [ ] OpenAI-enabled supported questions enter the model-led tool loop; no product-specific keyword shortcut bypasses OpenAI.
- [ ] Security preflight may reject secret extraction or clearly prohibited actions before OpenAI, with metadata stating the true mode.
- [ ] OpenAI mode supports at least one function call followed by a final model answer by default.
- [ ] The backend executes only allowlisted, schema-valid tools.
- [ ] Tool results are returned to OpenAI as `function_call_output`.
- [ ] The final answer is generated after tool execution and is grounded in typed result fields.
- [ ] Deterministic mode remains available and makes no OpenAI call.
- [ ] MCP remains LLM-independent and shares the canonical contracts/executor.
- [ ] Every executed tool turn and structured result is available in the HTTP response.
- [ ] Follow-up questions work through an explicit conversation identifier or documented bounded-history mechanism.
- [ ] Conversation ownership is checked against the authenticated principal.
- [ ] Tool errors sent to OpenAI are sanitized; internal exception details remain server-side.
- [ ] Numeric grounding is field-aware, unit-aware, and metric-aware—not global token matching.
- [ ] `get_position_greeks` supports instrument-family filtering and returns units/conventions.
- [ ] “Options delta” cannot return a cash equity merely because its absolute delta is larger.
- [ ] Assistant metadata distinguishes model-narrated, model-routed, deterministic, preflight-refused, and fallback modes truthfully.
- [ ] The React UI renders a message transcript, tool activity, clarification, errors, and follow-up turns.
- [ ] Network-free unit/integration/evaluation tests cover all behavior.
- [ ] A full backend, frontend, lint, type, build, and E2E gate passes after the PR is rebased.
- [ ] The PR contains no temporary Cursor tracking files or unrelated environment/UI fixes.

## Product rules

1. The model interprets, selects tools, and narrates. QuantLineage calculates.
2. No financial value may originate from model reasoning.
3. Do not send raw exceptions, secrets, database details, or stack traces to the model.
4. Do not expose arbitrary Python, SQL, shell, filesystem, network, or raw QuantLib objects.
5. Trading, order placement, and automatic portfolio mutation remain prohibited.
6. Side-effecting RiskRun submission remains disabled in conversational multi-tool mode unless separately approved and made idempotent.
7. The browser never receives `OPENAI_API_KEY`.
8. The public deterministic APIs remain usable without OpenAI.
9. Conversation state must be bounded, attributable, and deletable.
10. A fallback must never replay a tool that may already have executed.

## Conversation-state decision

Implement a provider-neutral application conversation id.

The application owns:

- conversation id;
- authenticated principal;
- bounded message/tool-turn history;
- latest OpenAI response id when available;
- created/updated timestamps;
- deletion and expiry policy.

The OpenAI adapter may use `previous_response_id` within a conversation, but the public API must not expose provider response ids as its conversation contract. This keeps the system testable and avoids locking the UI to one model provider.

For the first implementation, a bounded in-memory repository is acceptable only for local/demo mode. Shared deployment must use the existing persistence layer or explicitly document that conversations do not survive restarts.

## Grounding decision

Do not approve narration because a numeric token appears somewhere in an arbitrary payload.

Each tool must expose a typed grounding manifest containing:

- metric name;
- value;
- unit;
- sign convention;
- entity/position identity;
- source tool and field path;
- relevant run/snapshot identity.

The final narration validator must bind quantitative claims to those manifests. Dates, ids, counts, and unrelated metadata cannot ground a VaR or Greek claim.

If validation is uncertain, return the deterministic formatter plus structured results.

## Configuration

The deterministic provider remains the global default.

When the provider is explicitly `openai`, the normal assistant configuration must permit at least:

- model selection;
- one tool-selection response;
- one continuation after tool output;
- a hard total turn/tool budget;
- timeout and output-token limits.

Do not silently call the feature “model-narrated” when configured for one-shot routing.

## Success tests

The release gate must prove:

1. “What is VaR?” calls OpenAI, executes `get_var_es`, returns the output to OpenAI, and renders a grounded model answer.
2. “Which options have the largest delta?” calls OpenAI, executes the filtered Greek tool, and returns only options.
3. “What about gamma?” uses the prior conversational context.
4. “Compare VaR and limit utilization” may call more than one read-only tool and preserves both results.
5. A model-invented number is rejected even if the same token appears in a date, id, count, or unrelated field.
6. A tool exception exposes only a safe error code to OpenAI and the client.
7. Deterministic mode produces the established response without a network call.
8. Provider failure after tool execution does not replay the tool.

## References

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI conversation state](https://developers.openai.com/api/docs/guides/conversation-state)
- `docs/adr/006-llm-orchestrates-not-calculates.md`
- `docs/ai/openai_risk_assistant_design.md`
- `docs/ai/CONVERSATIONAL_ASSISTANT_TASKS.md`
