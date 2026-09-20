# Conversational Risk Assistant — Cursor Task Queue

Goal: [CONVERSATIONAL_ASSISTANT_GOAL.md](CONVERSATIONAL_ASSISTANT_GOAL.md)

Work exactly one unchecked task per loop iteration. The root agent may delegate bounded, non-overlapping subtasks to subagents, but the root agent owns integration, evidence, and the final commit.

## Status

- `[ ]` pending
- `[x]` complete
- `[!]` blocked; record the blocker and stop
- `[~]` in progress; only one root task may have this status

## Subagent operating contract

For each task:

1. Root reads the Goal, this queue, repository instructions, and current diff.
2. Root selects the first eligible unchecked task.
3. Root may spawn up to three specialist subagents.
4. Each subagent receives:
   - one concrete deliverable;
   - explicit read/write paths;
   - acceptance criteria;
   - instruction not to widen scope;
   - instruction not to commit or update this task file.
5. Parallel subagents must not edit overlapping paths.
6. Root reviews all findings/diffs, integrates, runs checks, records evidence, commits, and stops.
7. No subagent starts the next task.

Subagents should return findings with file/line references and test evidence. Read-only audit subagents are preferred whenever edits would overlap.

## Specialist roles

| Role | Primary responsibility | Normal write scope |
|---|---|---|
| architecture-auditor | Trace runtime flow and contract boundaries | Read-only |
| openai-loop | Responses function-call/output continuation | `backend/app/ai/openai_model.py`, `request_builder.py`, focused tests |
| orchestration | Provider selection and RiskQuery integration | `backend/app/ai/assistant.py`, `backend/app/risk/query.py` |
| quant-tools | Greek semantics, units, filters, deterministic services | `portfolio_service.py`, `tool_contracts.py`, quant tests |
| security-grounding | Error sanitization and claim grounding | `errors.py`, `narration.py`, security tests |
| conversation-state | Conversation repository and API contracts | new conversation modules, transport schemas, migrations |
| frontend-chat | Transcript and follow-up UX | `frontend/`, UI tests, E2E |
| qa-integrator | Regression matrix and final gate | Tests/docs only unless root approves a narrow fix |

Files `backend/app/risk/query.py`, `backend/app/ai/assistant.py`, API transport schemas, and this task queue are integration hotspots. Only the root or one designated subagent may edit an integration hotspot in a given iteration.

---

## C00 — Reproduce and trace the current behavior

- [ ] Establish a verified baseline for PR #6 and reproduce the “not really AI” experience.

Dependencies: none

Recommended subagents, all read-only:

- architecture-auditor: trace UI → API → provider → tool → formatter;
- openai-auditor: trace one-shot versus bounded Responses calls;
- quant-auditor: inspect `get_position_greeks` correctness;
- security-auditor: inspect errors and numeric grounding.

Acceptance:

- Reproduce one one-shot OpenAI request and record whether tool output returns to the model.
- Reproduce one bounded request with `AI_MAX_TOOL_ROUNDS=2`.
- Prove whether Greek questions call OpenAI.
- Record every path that can return `mode=model-routed` without an OpenAI call.
- Record current conversation-state behavior.
- Run PR #6 targeted tests and the relevant frontend test.
- No product-code changes.
- Add evidence below and stop.

Checks:

```bash
cd backend
python3 -m pytest   tests/test_ai_bounded_http.py   tests/test_ai_provider_integration.py   tests/test_position_greeks_tool.py   tests/test_ai_narration_grounding.py -q
cd ../frontend
npm test -- --run src/components/RiskQuery.test.jsx
```

Evidence:

## C01 — Freeze the conversational architecture contract

- [ ] Add an ADR or update the AI design with the final model-led request flow.

Dependencies: C00

Recommended subagents:

- architecture-auditor drafts the flow and mode definitions;
- security-grounding reviews trust boundaries;
- quant-tools reviews deterministic calculation boundaries.

Acceptance:

- Define the exact sequence for zero, one, and multiple function calls.
- Define `function_call_output` continuation behavior.
- Define the role of MCP as an external adapter, not an internal transport hop.
- Define assistant modes:
  - `model-narrated`;
  - `model-routed`;
  - `deterministic`;
  - `preflight-refused`;
  - `fallback`.
- Define tool/turn budgets and side-effect rules.
- Define conversation ownership, expiry, and provider-neutral ids.
- Define the grounding manifest contract.
- No application behavior changes.

Checks:

```bash
rg -n "model-narrated|function_call_output|conversation|grounding manifest" docs
```

Evidence:

## C02 — Remove model-path deterministic shortcuts

- [ ] Ensure supported OpenAI-mode questions enter the model-led flow.

Dependencies: C01

Primary owner: orchestration  
Read-only reviewer: security-grounding

Acceptance:

- Remove Greek/product keyword short-circuits from `answer_with_model` and `answer_with_bounded_assistant`.
- Keep deterministic routing only for `AI_PROVIDER=deterministic` and documented preflight security rejections.
- OpenAI chooses `get_position_greeks` from the strict tool schema.
- Metadata never says `model-routed` or `model-narrated` when no model call occurred.
- Add tests that fail if OpenAI is bypassed for delta/gamma/vega questions.
- Existing deterministic router behavior remains compatible.

Checks:

```bash
cd backend
python3 -m pytest   tests/test_ai_provider_integration.py   tests/test_ai_bounded_http.py   tests/test_position_greeks_tool.py   tests/test_ai_query_orchestration.py -q
```

Evidence:

## C03 — Make tool-output continuation the normal OpenAI experience

- [ ] Guarantee one tool call can be followed by a final model answer.

Dependencies: C02

Primary owners with isolated paths:

- openai-loop: request/continuation adapter and focused tests;
- orchestration: loop termination and HTTP response integration.

Do not let both owners edit the same file concurrently.

Acceptance:

- OpenAI mode defaults to enough model turns for one tool call plus final narration.
- Configuration semantics distinguish model turns from executed tool calls.
- A tool call on the final permitted turn does not silently end without a continuation; either reserve a narration turn or define separate budgets.
- The application sends every executed result as `function_call_output`.
- Final text is parsed only after tool output.
- One-shot router mode, if retained, is explicit and never presented as chat.
- Side-effecting tools remain disabled in the conversational loop.
- Provider failure after execution returns a partial safe result without replay.

Checks:

```bash
cd backend
python3 -m pytest   tests/test_ai_bounded_assistant.py   tests/test_ai_bounded_http.py   tests/test_openai_model.py   tests/test_openai_request_builder.py   tests/test_ai_config.py -q
```

Evidence:

## C04 — Sanitize tool failures before model continuation

- [ ] Prevent internal exception text from entering model or client payloads.

Dependencies: C01

Primary owner: security-grounding  
Read-only reviewer: orchestration

Acceptance:

- Replace raw `str(exc)` function outputs with a typed safe error:
  - stable public code;
  - retryable boolean;
  - safe user-facing message.
- Preserve full exception details only in redacted server logs.
- Explicitly cover database errors, provider errors, validation errors, missing RiskRuns, and unknown exceptions.
- API keys, tokens, SQL, file paths, stack traces, and private identifiers do not reach OpenAI.
- Tests use sentinel secrets and internal paths.

Checks:

```bash
cd backend
python3 -m pytest tests/test_ai_security.py tests/test_ai_bounded_assistant.py -q
```

Evidence:

## C05 — Replace token grounding with typed claim grounding

- [ ] Implement field-aware, unit-aware quantitative narration validation.

Dependencies: C01, C03

Primary owner: security-grounding  
Read-only reviewers: quant-tools and architecture-auditor

Acceptance:

- Introduce a typed grounding manifest for each successful tool result.
- Bind metric, value, unit, entity, sign convention, and source field path.
- Dates, ids, years, counts, and unrelated metadata cannot ground financial claims.
- Fraction-to-percent conversion is allowed only for explicitly percentage-valued fields.
- Test the attack: a year or id matching an invented VaR must be rejected.
- Test the attack: a delta value cannot ground a VaR claim.
- Test rounding and formatting tolerances explicitly.
- On rejection, return deterministic formatting plus structured tool results.
- Remove or retire global numeric-token approval logic.

Checks:

```bash
cd backend
python3 -m pytest   tests/test_ai_narration_grounding.py   tests/test_ai_multi_tool_evals.py   tests/test_ai_security.py -q
```

Evidence:

## C06 — Correct and type the position-Greeks tool

- [ ] Make Greek ranking quantitatively meaningful and auditable.

Dependencies: C01

Primary owner: quant-tools  
Read-only reviewer: security-grounding

Acceptance:

- Add typed arguments:
  - `greek`;
  - `top_n`;
  - optional `instrument_types` or a clear `options_only` flag;
  - ranking basis if more than absolute-value ranking is supported.
- “Options delta” returns only supported option families.
- A generic “position delta” may return all supported positions.
- Return typed rows and report metadata rather than an untyped dictionary.
- Return unit/convention for delta, gamma, vega, DV01, and FX delta.
- Document how each Greek is scaled by the pricing engine.
- Include portfolio id, market snapshot id, pricing engine/model identity where available.
- Do not expose raw QuantLib objects or accept free-form model parameters.
- Add mixed-portfolio tests proving equities cannot win an options-only query.

Checks:

```bash
cd backend
python3 -m pytest   tests/test_position_greeks_tool.py   tests/test_quantlib_adapter.py   tests/test_ai_query_orchestration.py -q
```

Use the repository’s actual QuantLib adapter test filename if different.

Evidence:

## C07 — Preserve the complete investigation result

- [ ] Return every executed tool turn, not only the last result.

Dependencies: C03, C04, C05

Primary owner: orchestration  
Read-only reviewer: API-contract reviewer

Acceptance:

- Add a typed investigation response containing ordered turns.
- Each turn includes:
  - tool name;
  - validated arguments safe for the client;
  - success/error status;
  - structured result or safe error;
  - grounding manifest;
  - provenance.
- Existing `data.tool_result` may remain as a backward-compatible last-result alias.
- Do not expose provider response ids, raw prompts, chain-of-thought, secrets, or raw exceptions.
- Two-tool integration test proves both results reach the client.

Checks:

```bash
cd backend
python3 -m pytest   tests/test_ai_bounded_http.py   tests/test_api_typed_models.py   tests/test_api_openapi_examples.py -q
```

Evidence:

## C08 — Add provider-neutral conversation state

- [ ] Support follow-up questions with an application-owned conversation id.

Dependencies: C03, C07

Primary owner: conversation-state  
Read-only reviewers: security-grounding and persistence reviewer

Acceptance:

- Request accepts an optional application `conversation_id`.
- First turn creates a conversation and returns its id.
- Follow-up turns load bounded prior context and preserve ownership.
- The OpenAI adapter may use `previous_response_id`, but the client contract remains provider-neutral.
- A conversation belonging to another principal fails closed.
- Define maximum turns/tokens, expiry, deletion, and restart behavior.
- Local/demo repository and shared persistence behavior are explicit.
- Tool calls and outputs are recorded without secrets or chain-of-thought.
- “What about gamma?” after an options-delta question resolves correctly.
- Tests do not call the network.

Checks:

```bash
cd backend
python3 -m pytest   tests/test_ai_conversations.py   tests/test_ai_provider_integration.py   tests/test_api_typed_models.py -q
```

Evidence:

## C09 — Convert the Risk Query UI into a chat transcript

- [ ] Add multi-turn conversational UX without exposing implementation internals.

Dependencies: C07, C08

Primary owner: frontend-chat  
Read-only reviewer: accessibility/UX subagent

Acceptance:

- Render ordered user and assistant messages.
- Retain the returned `conversation_id` for follow-ups.
- Render tool activity compactly: tool label, status, provenance link, and expandable structured result.
- Do not display raw tool schemas, raw provider responses, prompts, chain-of-thought, or API credentials.
- Clarification is shown as an assistant turn, not a terminal error.
- Loading, cancellation, retry, fallback, and partial-result states are distinct.
- Provide “New conversation” that clears local conversation state.
- Existing deterministic mode remains usable.
- Add accessibility labels and keyboard behavior.

Checks:

```bash
cd frontend
npm test -- --run src/components/RiskQuery.test.jsx
npm run lint
npm run build
cd ../e2e
npx playwright test tests/risk-query.spec.ts
```

Evidence:

## C10 — Add conversational and adversarial evaluations

- [ ] Prove the assistant is useful, grounded, and safe over multiple turns.

Dependencies: C04–C09

Primary owner: qa-integrator  
Recommended read-only subagents:

- quant-eval designer;
- prompt-injection/red-team reviewer;
- conversation-state reviewer.

Minimum cases:

- 10 single-tool questions with model narration;
- 8 multi-tool investigations;
- 8 follow-up questions requiring prior context;
- 6 option/Greek filtering cases;
- 8 numeric-grounding attacks;
- 6 tool-error/timeout/fallback cases;
- 6 prompt-injection/secret-extraction cases;
- 4 cross-principal conversation-access cases.

Acceptance:

- Every financial number maps to an allowed grounding manifest.
- Every executed tool is allowlisted and schema-valid.
- No secret or raw exception appears in model/client payloads.
- No tool executes twice because of retry/fallback.
- Follow-up intent accuracy and tool-selection thresholds are documented.
- All tests are network-free.

Checks:

```bash
cd backend
python3 -m pytest tests/test_ai_conversational_evals.py tests/test_ai_security.py -q
```

Evidence:

## C11 — Align configuration, documentation, and PR scope

- [ ] Remove configuration ambiguity and unrelated changes.

Dependencies: C03, C08, C09

Primary owner: root  
Read-only subagents: docs/config auditor and PR-scope auditor

Acceptance:

- Choose one canonical env naming scheme and use it consistently in:
  - code;
  - `.env.example`;
  - Compose;
  - operator guide;
  - PR body.
- Document the distinction between router mode and conversational mode.
- Document conversation retention and data-handling implications.
- Remove `.cursor/DEFERRED_NOT_DONE.md` and other temporary agent artifacts.
- Move unrelated Vite proxy/E2E navigation fixes to a separate PR unless required by the chat implementation.
- Update setup and rollback instructions.
- Cite official OpenAI documentation for function calling and conversation state.

Checks:

```bash
rg -n "AI_PROVIDER|OPENAI_MODEL|MAX_TOOL_ROUNDS|QUANTLINEAGE_AI" .
git diff --check
```

Evidence:

## C12 — Run the merge gate

- [ ] Verify the complete corrective goal and prepare a focused merge summary.

Dependencies: C00–C11

Primary owner: qa-integrator  
Root owns final decision.

Acceptance:

- Every Definition of Done item in the Goal is checked with evidence.
- Full backend suite passes.
- Ruff and mypy pass under repository policy.
- Full frontend tests, lint, and production build pass.
- Relevant Playwright E2E tests pass.
- Compose renders without exposing secrets to the frontend.
- Normal CI performs no OpenAI network call.
- Opt-in live smoke proves tool call → function output → final narration.
- PR is rebased on its intended base and mergeable.
- PR summary reports full-suite evidence after the final rebase.
- Remaining limitations are explicit.
- Root reviews the final diff for accidental agent artifacts and unrelated files.

Checks:

```bash
cd backend
python3 -m pytest -q
ruff check app tests
mypy app
cd ../frontend
npm test -- --run
npm run lint
npm run build
cd ../e2e
npx playwright test tests/risk-query.spec.ts
cd ..
docker compose config
git diff --check
```

Evidence:

---

## Global stop conditions

Stop the current loop and request a decision if:

- a model path would calculate or transform financial risk outside deterministic code;
- a tool would expose raw QuantLib objects or unrestricted model parameters;
- conversation state cannot enforce principal ownership;
- a fallback could replay side-effecting work;
- numeric claims cannot be tied to typed metric/unit/source fields;
- implementation requires putting an OpenAI key in the browser;
- a subagent needs to edit a file currently owned by another active subagent;
- the full baseline is red for an unrelated reason;
- the public API must break without an explicit migration decision.
