# ADR 009: Grounded conversational risk assistant contract

- Status: Accepted (operating contract; implementation C02–C12)
- Date: 2026-09-20
- Owners: Lead Architect; AI Orchestration Engineer
- Depends on: [ADR 006](006-llm-orchestrates-not-calculates.md)
- Goal: [CONVERSATIONAL_ASSISTANT_GOAL.md](../ai/CONVERSATIONAL_ASSISTANT_GOAL.md)
- Baseline: C00 evidence in [CONVERSATIONAL_ASSISTANT_TASKS.md](../ai/CONVERSATIONAL_ASSISTANT_TASKS.md)

## Context

PR #6 ships an opt-in OpenAI path, but C00 showed it is still a one-shot
intent router: default `AI_MAX_TOOL_ROUNDS=1` never returns tool output to the
model; Greek and secret short-circuits stamp `mode=model-routed` with zero
provider calls; `get_position_greeks` ranks all cash deltas with no options
filter; narration grounding is a global numeric-token bag; tool failures can
reach OpenAI as `str(exc)`; there is no application conversation id.

ADR 006 remains binding: the model orchestrates; QuantLineage calculates.
This ADR freezes the *conversational* contract that C02–C12 implement. C01
does not change application behavior.

Official references:

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI conversation state](https://developers.openai.com/api/docs/guides/conversation-state)

## Decision

### 1. Runtime flow

```text
UI question
  -> POST /api/v1/risk/query (optional application conversation_id)
  -> backend assistant orchestrator
  -> security preflight (may refuse before OpenAI)
  -> OpenAI Responses API
  -> validate_tool_call against TOOL_CONTRACTS
  -> shared execute_allowlisted_tool (in-process)
  -> PricingEngine / PortfolioService / risk engines
  -> function_call_output returned to OpenAI
  -> grounded natural-language answer
  -> UI conversation transcript
```

MCP remains an **external** stdio adapter over the same `TOOL_CONTRACTS`,
`validate_tool_call`, and `execute_allowlisted_tool`. The in-process HTTP
assistant must not spawn MCP, import it as a transport hop, or duplicate
executor logic.

`AI_PROVIDER=deterministic` remains the global default and makes no OpenAI
call.

### 2. Function-call sequences (OpenAI-enabled HTTP path)

Per Responses `create`, at most one function call unless a later ADR changes
that. The application owns the loop.

| Model function calls | Sequence | Provider called? |
|---|---|---|
| Zero | Documented security/policy **preflight** may refuse before any provider call. Otherwise the model may refuse, clarify, or answer with no tool. No executor call. | No for preflight. Yes for model refuse/clarify/text. |
| One | Model turn selects one allowlisted tool → validate → execute → append `function_call_output` → **reserved narration continuation** → grounded final answer (or deterministic formatter + structured results if grounding fails). | Yes: at least select + continue. |
| Multiple | Repeat select → execute → `function_call_output` → continue within budgets. Every executed result is sent. Final text is parsed only after tool output. | Yes for every select and continue turn. |

Product-keyword shortcuts (including Greeks) must not bypass OpenAI on the
OpenAI-enabled path. They are not security preflight.

### 3. `function_call_output` continuation

1. After every executed tool (success or sanitized error), the application
   appends a Responses `function_call_output` item (`call_id` + output string).
2. Continuation uses adapter-internal `previous_response_id`. The public API
   must not expose provider response ids as the conversation contract.
3. **Model-turn budget** and **tool-call budget** are distinct. A tool
   selection on the last permitted *tool* slot must still reserve a narration
   model turn. The loop must not execute a last-round tool and stop with
   `round_limit` without sending that output to OpenAI.
4. Default OpenAI conversational configuration must allow at least one
   tool-selection turn, one continuation after tool output, a hard total cap,
   timeout, and output-token limit.
5. Explicit one-shot **router** mode may be retained only as a named
   configuration. It is never presented as chat and never labeled
   `model-narrated`.
6. Provider failure after execution returns a partial safe result and **does
   not replay** any tool that may already have run.

### 4. Assistant modes (truthful; never lie)

| Mode | Legal when |
|---|---|
| `model-narrated` | At least one provider call **and** a final natural-language answer after tool output, with grounding accepted. |
| `model-routed` | Explicit one-shot router: model selected a tool; the application formatted the answer deterministically. Not chat. |
| `deterministic` | `AI_PROVIDER=deterministic` or no model wired. Keyword `RiskQueryEngine`. No OpenAI call. |
| `preflight-refused` | Documented security/policy rejection **before** OpenAI (secret extraction, clearly prohibited actions). |
| `fallback` | Provider/config/parse failure. Deterministic router only if **no** tool has executed; otherwise partial safe result. `fallback=true`. |

`model-routed` and `model-narrated` are allowed only after a provider call for
that request. UI badges must key off `mode`, not merely `provider === "openai"`.

### 5. Tool / turn budgets and side effects

- Conversational OpenAI mode: at least one tool-selection model turn and one
  continuation; hard cap on model turns and executed tools (current ceiling
  remains four unless configuration says otherwise).
- Side-effecting tools are **disabled** in the conversational loop unless
  separately approved **and** made idempotent. That set includes every tool
  that submits or enqueues a RiskRun, at minimum: `run_portfolio_risk`,
  `run_stress`, and `get_top_risk_contributors`.
- Heavy RiskRuns are not automatically replayed or polled inside the assistant
  request. Return a run id and use existing workers.
- Trading, order placement, and automatic portfolio mutation remain prohibited.

### 6. Conversation ownership

The application owns a **provider-neutral `conversation_id`**.

The application also owns: authenticated principal, bounded message/tool-turn
history, optional latest provider response id (adapter-private), created/updated
timestamps, expiry, and deletion.

- Follow-up turns load bounded prior context and check ownership against the
  authenticated principal. Cross-principal access fails closed.
- Local/demo may use a bounded in-memory repository.
- Shared deployment must use the existing persistence layer **or** explicitly
  document that conversations do not survive restarts.
- Conversation records must not store secrets, raw prompts, chain-of-thought,
  or unsanitized exceptions.

### 7. Grounding manifest contract

Do not approve narration because a numeric token appears somewhere in a payload.

Each successful tool result exposes a typed **grounding manifest** of claims:

- metric name;
- value;
- unit;
- sign convention;
- entity/position identity;
- source tool and field path;
- relevant run/snapshot identity.

The narration validator binds quantitative claims to those manifests. Dates,
ids, years, counts, confidence, and unrelated metadata cannot ground a VaR or
Greek claim. Fraction-to-percent conversion is allowed only for fields
explicitly declared percentage-valued.

If validation is uncertain, return the deterministic formatter plus structured
tool results. Global numeric-token matching is retired (C05).

Tool errors sent to OpenAI or the client are a typed safe error only: stable
public code, `retryable` boolean, safe message. Raw `str(exc)`, SQL, file
paths, stack traces, keys, and private identifiers stay in redacted server
logs (C04).

### 8. Deterministic calculation boundary

ADR 006 is unchanged. All prices, Greeks, VaR, ES, stress, limits, and DV01
originate from `PricingEngine`, `PortfolioService`, and risk engines. The model
must not calculate, estimate, interpolate, or fill in financial values.

`TOOL_CONTRACTS` remains the canonical allowlist for HTTP, OpenAI strict
schemas, and MCP. Unknown or schema-invalid tools execute nothing.

Target `get_position_greeks` contract (implemented in C06, not C01):

- Typed args: `greek`, `top_n`, optional `instrument_types` or `options_only`,
  and an explicit ranking basis if anything other than absolute value is added.
- Generic “position delta” may include all families that populate the Greek.
- “Options delta” / `options_only` returns only supported option families.
  Cash equity or futures must not win because `abs(delta)` is larger.
- Typed rows plus report metadata: portfolio id, market snapshot id, pricing
  engine identity, selected greek, applied filter, ranking basis.
- Units/conventions match Builtin/QuantLib adapter scaling and
  `backend/app/risk/sensitivities.py`: cash delta `S·∂V/∂S`; dollar gamma
  `S²·∂²V/∂S²`; vega as P&L per 1 vol point (`0.01`); DV01 as P&L for +1bp;
  cash FX delta.
- No raw QuantLib objects and no free-form model parameters.

`OPENAI_API_KEY` is server-only. It never appears in UI, `VITE_*`, MCP, logs,
tool arguments, model inputs, HTTP responses, or conversation records.

Portfolio text, instrument labels, user questions, and tool outputs are
untrusted data. Injected instructions in that data authorize nothing.

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Keep one-shot router as the advertised OpenAI chat | C00: tool output never returns to the model; not the product. |
| Stamp `model-routed` whenever `AI_PROVIDER=openai` | Lies about the trust boundary (C00 Greek/secret short-circuits). |
| Token-bag numeric grounding | Years, ids, counts, and confidence can approve invented VaR/Greek claims. |
| LLM estimates Greeks/VaR when tools fail | Violates ADR 006. |
| Public API uses OpenAI `previous_response_id` as conversation id | Locks the UI to one provider; not testable offline. |
| HTTP assistant calls MCP as an internal hop | Duplicates transport; MCP stays an external adapter. |
| Expose raw QuantLib handles as tools | T24 rejected; allowlist + `PricingEngine` only. |

## Consequences

- **C02** removes OpenAI-path Greek/product short-circuits and stops labeling
  responses `model-routed` / `model-narrated` when no model call occurred.
- **C03** makes select → execute → `function_call_output` → narrate the default
  OpenAI experience, with separate turn/tool budgets and last-round narration
  reservation.
- **C04** sanitizes tool failures before model continuation.
- **C05** replaces token grounding with typed claim manifests.
- **C06** implements the filtered, unit-bearing `get_position_greeks` contract.
- **C07–C09** return every tool turn, add provider-neutral conversation state,
  and render a transcript.
- UI, OpenAPI, and config must distinguish conversational (`model-narrated`)
  from explicit router (`model-routed`) and from `preflight-refused`.
- No application behavior changes in this ADR itself.

## Current gaps this contract forbids (C00)

| Contract | Current gap |
|---|---|
| No model call ⇒ not `model-routed` / `model-narrated` | Prefixed `model-routed` then short-circuit: `backend/app/risk/query.py` ~824–865, ~983–1024 |
| Default = tool + narration continuation | Default `AI_MAX_TOOL_ROUNDS=1` one-shot: `backend/app/ai/config.py`, `portfolio_service.py` ~548–554 |
| Every executed result → model | Last-round skip: `backend/app/ai/assistant.py` ~259–272 |
| Modes include `model-narrated` and `preflight-refused` | Schema only `model-routed` \| `deterministic` \| `fallback` |
| `get_top_risk_contributors` is side-effecting | Submits a RiskRun but is outside `SIDE_EFFECTING_TOOLS` |
| Provider-neutral `conversation_id` | `RiskQueryRequest` is `{portfolio, question}` only |
| Options-only Greeks | Abs cash-delta ranking over all positions; no family filter |
| Typed grounding manifests | Global token bag in `backend/app/ai/narration.py` |
| Sanitized tool errors | Raw `str(exc)` in `assistant.py` ~342–356 |
| MCP not on the HTTP hop | Already true (`backend/app/mcp.py`); keep |
