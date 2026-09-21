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

- [x] Establish a verified baseline for PR #6 and reproduce the “not really AI” experience.

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

- Baseline HEAD: `6fd80cc` (`docs: add Cursor Cloud subagent kickoff prompt`) on `origin/cursor/risk-query-incomplete-fallback-bebd` (PR #6 vs `cursor/openai-risk-assistant`). No AGENTS.md in repo. Product code unchanged in this iteration.
- Checks (2026-09-20, Python 3.12.3; frontend command as specified, vitest already uses `run`):
  - `cd backend && python3 -m pytest tests/test_ai_bounded_http.py tests/test_ai_provider_integration.py tests/test_position_greeks_tool.py tests/test_ai_narration_grounding.py -q` → **24 passed** in 1.84s.
  - `cd frontend && npm test -- --run src/components/RiskQuery.test.jsx` → **9 passed** (1 file) in 1.21s.
  - Baseline is green for C00 scope; not blocked.

### Runtime flow

1. UI `RiskQuery.submit` → `askRisk(portfolio, question)` → `POST /api/v1/risk/query` (`frontend/src/api.js:210-216`). Request fields are only `portfolio` and `question`.
2. `PortfolioService.query` (`backend/app/services/portfolio_service.py:531-554`): no model → `RiskQueryEngine.answer`; `AI_MAX_TOOL_ROUNDS==1` (default) → `answer_with_model`; `max_tool_rounds>1` and `continue_after_tools` → `answer_with_bounded_assistant`.
3. Both OpenAI HTTP paths stamp `assistant.mode="model-routed"` **before** any model call (`query.py:824-828`, `983-987`).
4. One-shot: `OpenAIRiskAssistantModel.complete` (Responses `create`) → `validate_tool_call` → `_execute_tool` → deterministic `_format_answer`. Tool JSON never re-enters the model (`OneShotRiskAssistant` / `answer_with_model:949-957`).
5. Bounded: `BoundedRiskAssistant.run` → `complete`, local execute, `continue_after_tools(previous_response_id, function_call_output)`, stop on final/clarify/refuse or `round_index >= max_rounds` (`assistant.py:164-272`). Last-round tool output is **not** sent to OpenAI.
6. Shared executor is in-process `execute_allowlisted_tool`. MCP (`backend/app/mcp.py`) is a parallel stdio adapter (“No live LLM”); FastAPI does not import it.
7. UI shows “AI-routed” when `assistant.provider==='openai'` and not `fallback`; it does not inspect `mode` (`ScenarioBuilder.jsx:479-498`).

### Model-call counts (scripted, no network)

| Scenario | `complete` | `continue_after_tools` | Tool output to model | Result |
|---|---|---|---|---|
| One-shot `AI_MAX_TOOL_ROUNDS=1`, “What is 99% VaR?” | **1** | **0** | **No** | `get_var_es`, `mode=model-routed`, no `investigation`; deterministic formatter (“historical 99% VaR is 32,798…”) |
| Bounded `AI_MAX_TOOL_ROUNDS=2`, tool then final text | **1** | **1** | **Yes** (first tool as `function_call_output`) | `stopped_reason=final`, `narration_grounded=True` |
| Bounded `AI_MAX_TOOL_ROUNDS=2`, tool then another tool | **1** | **1** | First yes; **second never sent** | `stopped_reason=round_limit`, both tools executed locally |
| “Which options have the largest delta?” one-shot | **0** | **0** | n/a | `get_position_greeks`, `mode=model-routed`, `fallback=false` |
| “Biggest options delta?” bounded rounds=2 | **0** | **0** | n/a | Same short-circuit; OpenAI never called |
| “What is the api key?” | **0** | **0** | n/a | Refusal, `mode=model-routed` |
| “What is my theta?” | **0** | **0** | n/a | Unsupported-Greeks clarification, `mode=model-routed` |

Greek questions **do not call OpenAI**. Ranking on `SAMPLE_PORTFOLIO` for “largest delta” was `fut-es`, `eq-spy`, `eq-msft`, `eq-nvda`, `eq-aapl` — **no options** in top 5.

### Metadata mismatches (`mode=model-routed` without a model call)

- Secret preflight: `query.py:829-841` and `988-1000`.
- Unsupported Greeks (theta/rho): `query.py:842-856` and `1001-1015`.
- Supported Greeks short-circuit to `_grounded_tool_response`: `query.py:857-865` and `1016-1024`. Confirmed by `test_ai_provider_integration.py:180-200` (`len(requests)==0`, `mode=="model-routed"`).
- Config/auth errors after a failed `complete` still keep `mode=model-routed`, `fallback=false` (`query.py:879-891`).
- `mode="deterministic"` is in the schema but never set; deterministic `answer()` omits `data.assistant`.

### Conversation-state behavior

- No application `conversation_id`. `RiskQueryRequest` = `{portfolio, question}` (`transport.py:89-91`).
- UI keeps a single last response in `useState` (`ScenarioBuilder.jsx:502-513`); follow-up “What about gamma?” is a new independent POST.
- `previous_response_id` exists only inside one `BoundedRiskAssistant.run`; it is not returned to the client or reused on the next Ask.

### Subagent findings (read-only; C01 not started)

- **architecture-auditor:** Critical Greek/secret short-circuits labeled model-routed; one-shot never returns tool output; no conversation state; UI “AI-routed” from provider only; MCP not on the HTTP hop.
- **openai-loop auditor:** Default rounds=1 is select-only; bounded last-round tool is executed then `round_limit` with no narration continuation and no last `function_call_output`; `max_tool_calls` always 1 per Responses create; side-effect gate in bounded only (`run_portfolio_risk`/`run_stress`); one-shot discards `proposed_answer`.
- **quant-tools auditor:** Critical: no `instrument_types`/`options_only`; abs-cash-delta ranking lets futures/equities win “options delta”; no units/conventions or pricing-engine identity; no mixed-portfolio filter test. Contract args are only `greek` and `top_n` (`tool_contracts.py:138-144`).
- **security-grounding auditor:** Important: tool failures sent to OpenAI as raw `str(exc)` (`assistant.py:342-356`); numeric grounding is a global token bag (`narration.py:41-75`) so year/id/count/confidence can ground VaR/Greek claims; `get_top_risk_contributors` submits a RiskRun but is not in `SIDE_EFFECTING_TOOLS`. Key handling on API/MCP/frontend is otherwise clean; bounded post-tool fallback does not replay tools that landed in `executed`.

Next eligible task: **C01** (not started).

## C01 — Freeze the conversational architecture contract

- [x] Add an ADR or update the AI design with the final model-led request flow.

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

- Contract: `docs/adr/009-grounded-conversational-risk-assistant.md` (Accepted operating contract; implementation C02–C12). Indexed in `docs/adr/README.md`. Pointer in `docs/ai/openai_risk_assistant_design.md` and `docs/ai/CONVERSATIONAL_ASSISTANT_GOAL.md`.
- Subagents (read-only drafts; root wrote the ADR):
  - architecture-auditor: zero/one/many function-call sequences; `function_call_output` + reserved narration turn; MCP external; truthful modes; distinct model-turn vs tool-call budgets; provider-neutral `conversation_id`.
  - security-grounding: `preflight-refused` vs model modes; typed safe errors; grounding-manifest schema; no fallback replay; server-only key; untrusted portfolio/tool data.
  - quant-tools: ADR 006 binding; `get_position_greeks` filter/units/engine-identity target; `TOOL_CONTRACTS` canonical; no raw QuantLib; RiskRun submit disabled in the loop (including `get_top_risk_contributors`).
- Checks (2026-09-20): `rg -n "model-narrated|function_call_output|conversation|grounding manifest" docs` matches ADR 009 (including `model-narrated`, `function_call_output`, `conversation_id`, `grounding manifest`) plus index/design pointers. No backend/frontend product files changed.
- No application behavior changes.

Next eligible tasks after C01: **C02**, **C04**, and **C06** (this loop stops; first by queue order is C02).

## C02 — Remove model-path deterministic shortcuts

- [x] Ensure supported OpenAI-mode questions enter the model-led flow.

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

- Product fix HEAD: `b250a42` (`fix: send OpenAI-path Greek questions to the model (C02)`). Removed `_is_greeks_question` short-circuits from `answer_with_model` and `answer_with_bounded_assistant` (`backend/app/risk/query.py`). Deterministic `route()` still maps Greek questions. Secret extraction remains pre-OpenAI and is labeled `preflight-refused`. Config/auth errors after `complete()`/`run()` use `fallback` without executing tools. Successful model results stamp `model-routed` only after the provider call. Schema modes include `model-narrated` and `preflight-refused` (`transport.py`, `AssistantMode`).
- This run (no extra product-code change): closed remaining C02 coverage/evidence gaps.
  - Theta/rho are not security preflight; one-shot and bounded tests fail if those questions skip OpenAI.
  - Bounded secret preflight asserts `complete_count==0` and `preflight-refused`.
  - Deterministic router still clarifies theta/rho with no `assistant` metadata.
  - Tests: `21d8ddd` (`test: prove OpenAI-path theta/rho questions are not preflight shortcuts (C02)`).
- Security-grounding reviewer: keep `_is_secret_request`; theta/rho are not security preflight; SIDE_EFFECTING expansion is C03 scope.
- Checks (2026-09-20, Python 3.12.3), fresh after the test commit and again after a temporary bypass restore:
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_ai_provider_integration.py tests/test_ai_bounded_http.py tests/test_position_greeks_tool.py tests/test_ai_query_orchestration.py -q
  ```
  → **45 passed**, 1 warning, exit code **0** (1.43s).
  Related suites `tests/test_ai_evals.py tests/test_ai_security.py tests/test_api_typed_models.py tests/test_api_openapi_examples.py tests/test_risk_query_api_incomplete.py` → **150 passed**, exit code **0**.
  Bypass proof: restoring the old `_is_greeks_question` OpenAI-path short-circuit fails 7 tests (delta/gamma/vega, theta/rho, bounded greeks/theta); deterministic theta/rho still passes.
- C02 SHAs on `cursor/risk-query-incomplete-fallback-bebd`: product `b250a42`, tests `21d8ddd`, evidence `f23c533`.

Next eligible after this commit: **C03**, **C04**, and **C06**.

## C03 — Make tool-output continuation the normal OpenAI experience

- [x] Guarantee one tool call can be followed by a final model answer.

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

- Product HEAD: `0ccac58` (`feat: default OpenAI chat to tool output then reserved narration (C03)`). Conversational OpenAI defaults are `AI_ASSISTANT_LOOP=conversational`, `AI_MAX_TOOL_ROUNDS` (model turns) **2**, `AI_MAX_TOOL_CALLS` (executed tools) **1**. `AISettings.max_model_turns` aliases the model-turn budget. Explicit `AI_ASSISTANT_LOOP=router` is one-shot (`model-routed` only; never `model-narrated`).
- `BoundedRiskAssistant` always appends `function_call_output` and continues after an executed tool. A tool on the last permitted tool or model turn sets `reserve_narration` (`tool_choice=none`). Final text is parsed only on `continue_after_tools` (`allow_final_text=True`); `complete()` still treats text as clarification.
- HTTP: OpenAI + conversational uses the bounded loop even for one tool. Grounded narration stamps `model-narrated`. Provider error after execution still returns truncated fallback without replay.
- `SIDE_EFFECTING_TOOLS` includes `run_portfolio_risk`, `run_stress`, and `get_top_risk_contributors` (RiskRun submit).
- Checks (2026-09-20, Python 3.12.3), fresh:
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_ai_bounded_assistant.py tests/test_ai_bounded_http.py tests/test_openai_model.py tests/test_openai_request_builder.py tests/test_ai_config.py -q
  ```
  → **88 passed**, exit code **0** (2.75s).

Next eligible after this commit: **C04**, **C05**, and **C06**.

## C04 — Sanitize tool failures before model continuation

- [x] Prevent internal exception text from entering model or client payloads.

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

- Product HEAD: `cd9a5e8`. Tool failures sent to OpenAI as `{error: {code, retryable, message}}` via `safe_tool_error_payload`. Codes: `database_error`, `provider_error`, `validation_error`, `risk_run_not_found`, `unknown_error`. Raw `str(exc)` is logged with redacted secrets/paths/SQL (`log_tool_exception`).
- Checks (2026-09-20, Python 3.12.3), fresh:
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_ai_security.py tests/test_ai_bounded_assistant.py -q
  ```
  → **35 passed**, 1 warning, exit code **0** (1.37s).

## C05 — Replace token grounding with typed claim grounding

- [x] Implement field-aware, unit-aware quantitative narration validation.

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

- Product HEAD: `72e6d43`. Typed `GroundingClaim` manifests bind metric, value, unit, entity, field path, and optional percent-from-fraction. Years, ids, counts, and dates are not financial claims. Global numeric-token collection no longer approves invented VaR/Greeks. Attacks covered: year/id → VaR, delta → VaR. Rounding/`32,798` tolerated; `32000` is not. Fraction-to-percent only for ratio/percent fields. Rejection still uses the deterministic formatter.
- Checks (2026-09-20, Python 3.12.3), fresh:
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_ai_narration_grounding.py tests/test_ai_multi_tool_evals.py tests/test_ai_security.py -q
  ```
  → **45 passed**, 1 warning, exit code **0** (1.48s).

## C06 — Correct and type the position-Greeks tool

- [x] Make Greek ranking quantitatively meaningful and auditable.

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

- `get_position_greeks` args: `greek`, `top_n`, `options_only`, `ranking_basis=abs_value`. OpenAI strict schemas cannot carry arrays, so family filtering is the boolean `options_only` flag (option families: european_option, fx_option, cap_floor, swaption). Deterministic router sets `options_only` when the question mentions options.
- Report rows include `instrument_type`, `unit`, `convention`; report metadata includes `scale`, `pricing_engine`, portfolio and snapshot ids. Equities cannot win an options-only ranking on SAMPLE_PORTFOLIO. No QuantLib objects in the payload.
- Checks (2026-09-20, Python 3.12.3), fresh. Repo has `tests/test_quantlib_pricing.py` (no `test_quantlib_adapter.py`):
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_position_greeks_tool.py tests/test_quantlib_pricing.py tests/test_ai_query_orchestration.py -q
  ```
  → **69 passed**, 1 warning, exit code **0** (1.42s).

## C07 — Preserve the complete investigation result

- [x] Return every executed tool turn, not only the last result.

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

- Product HEAD: `d2b87e2`. Typed `RiskQueryInvestigation` / `InvestigationTurn` on the HTTP response: ordered turns with tool name, validated args, success/error, structured result or typed safe error, grounding manifest, and provenance. `data.tool_result` remains the last successful result alias. Extra fields (`provider_response_id`, `previous_response_id`, prompts, CoT) are forbidden. Partial provider-error fallback includes executed turns and does not replay tools.
- Checks (2026-09-20, Python 3.12.3), fresh:
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_ai_bounded_http.py tests/test_api_typed_models.py tests/test_api_openapi_examples.py -q
  ```
  → **66 passed**, 1 warning, exit code **0** (2.24s).

## C08 — Add provider-neutral conversation state

- [x] Support follow-up questions with an application-owned conversation id.

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

- Product HEAD: `47a2fb8`. Optional `RiskQueryRequest.conversation_id`; first turn creates `conv_*` and returns it on `data.conversation_id`. Follow-ups load bounded prior question/tool-args into the model request. Cross-principal access raises `ConversationAccessDenied`; unknown/expired ids raise `ConversationNotFound`. In-memory repo (`SURVIVES_RESTARTS=False`, TTL 24h, max 8 turns) is used for local/demo and the current shared process; provider `previous_response_id` is stored privately and never appears on the client contract. “What about gamma?” after options-delta selects `get_position_greeks` with `options_only=true`.
- Checks (2026-09-20, Python 3.12.3), fresh:
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_ai_conversations.py tests/test_ai_provider_integration.py tests/test_api_typed_models.py -q
  ```
  → **48 passed**, 1 warning, exit code **0** (2.02s).

## C09 — Convert the Risk Query UI into a chat transcript

- [x] Add multi-turn conversational UX without exposing implementation internals.

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

- Product HEAD: `31e6169`. Risk Query keeps a transcript of user/assistant turns, retains `conversation_id` on follow-ups, and renders compact expandable tool activity (label, status, provenance link, structured result). Mode badges use `assistant.mode` (`AI-narrated` / `AI-routed`). Clarification is an assistant turn. Loading, cancel, retry, fallback, and partial/truncated states are distinct. New conversation clears local state. No schemas, CoT, model names, or credentials in the UI. Deterministic worst-stress E2E still passes.
- Checks (2026-09-20), fresh:
  ```
  cd /workspace/frontend
  npm test -- --run src/components/RiskQuery.test.jsx
  npm run lint
  npm run build
  cd /workspace/e2e
  QUANTLINEAGE_E2E_UVICORN="python3 -m uvicorn" PLAYWRIGHT_USE_CHROMIUM=1 npx playwright test tests/risk-query.spec.ts
  ```
  → vitest **12 passed** (1 file); eslint exit **0**; vite build exit **0**; Playwright **1 passed**.

## C10 — Add conversational and adversarial evaluations

- [x] Prove the assistant is useful, grounded, and safe over multiple turns.

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

- Product HEAD: `770eb4b` (`tests/test_ai_conversational_evals.py`). Network-free suite counts: **10** single-tool narrated, **8** multi-tool investigations, **8** follow-ups (100% intent/tool-selection), **6** option/Greek filter, **8** numeric-grounding attacks, **6** timeout/fallback (no replay), **6** prompt-injection/secret, **4** cross-principal. Thresholds documented in the module: follow-up/tool-selection/grounding = 1.0. Secrets/raw exceptions stay off client payloads.
- Checks (2026-09-20, Python 3.12.3), fresh:
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_ai_conversational_evals.py tests/test_ai_security.py -q
  ```
  → **79 passed**, 1 warning, exit code **0** (1.79s).

## C11 — Align configuration, documentation, and PR scope

- [x] Remove configuration ambiguity and unrelated changes.

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

- Product HEAD: `522173d` (`docs: align canonical AI env names and conversational operator guide (C11)`). Canonical names are `AI_*` / `OPENAI_*` in code, `.env.example`, `.env.shared.example`, Compose (backend + worker), operator guide, and design snippet. `AI_ASSISTANT_LOOP=conversational` vs `router` documented. Conversation retention is in-memory, 24h TTL, max 8 turns, fail-closed ownership. `.cursor/DEFERRED_NOT_DONE.md` removed. Operator guide cites OpenAI function calling and conversation state. Historical T00–T24 queue in `docs/ai/TASKS.md` points at this file for conversational defaults.
- Unrelated Vite/E2E: `e2e` `#risk-query` / Risk Query nav is required because chat is its own section (C09). `frontend/.env.development` (`VITE_API_BASE_URL=same-origin`) was already on PR #6 (`dd291ac`); no OpenAI secret; cannot split to another PR on this branch.
- Checks (2026-09-20), fresh:
  ```
  rg -n "AI_PROVIDER|OPENAI_MODEL|MAX_TOOL_ROUNDS|QUANTLINEAGE_AI" .
  git diff --check
  ```
  → `QUANTLINEAGE_AI` appears only as “do not introduce aliases” in the operator guide plus this check command. `git diff --check` exit **0**.

## C12 — Run the merge gate

- [ ] Verify the complete corrective goal and prepare a focused merge summary.

Dependencies: C00–C11, C13–C19

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

> Historical evidence only. C12 was reopened after review of HEAD `b70fccd`. Do not mark it complete until C13–C19 are complete and every C12 acceptance item is rerun on the new final HEAD.

- Live-smoke HEAD: `a5d3337` (`test: prove live OpenAI smoke is tool output then narration (C12)`). Opt-in test now does `complete` → canned `function_call_output` → `proposed_answer`. Skipped without `RUN_LIVE_AI_TESTS=1`.
- Merge-base with `origin/cursor/openai-risk-assistant` is `0b6a4dc` (that tip); no rebase required. `gh pr view 6`: `MERGEABLE` / `CLEAN`, base `cursor/openai-risk-assistant`.
- Goal DoD items checked in `CONVERSATIONAL_ASSISTANT_GOAL.md`. Cursor Cloud goal status is not marked from this agent.
- Remaining limitations in `docs/ai/MERGE_SUMMARY.md`: in-memory conversations, one-tool conversational default, live smoke not run in this environment, Vite `frontend/.env.development` already on PR #6.
- Checks (2026-09-20, Python 3.12.3), fresh after `a5d3337`:
  ```
  cd /workspace/backend && python3 -m pytest -q
  ruff check app tests
  python3 -m mypy app/ai --follow-imports=silent
  cd /workspace/frontend && npm test -- --run && npm run lint && npm run build
  cd /workspace/e2e && QUANTLINEAGE_E2E_UVICORN="python3 -m uvicorn" PLAYWRIGHT_USE_CHROMIUM=1 npx playwright test tests/risk-query.spec.ts
  docker compose -f docker-compose.yml config
  POSTGRES_PASSWORD=dummy-ci QUANTLINEAGE_API_TOKEN=dummy-token docker compose -f docker-compose.shared.yml config
  git diff --check
  ```
  → pytest **2158 passed**, 10 skipped; ruff clean; mypy `app/ai` silent Success; vitest **215 passed**; eslint 0; vite build 0; Playwright **1 passed**; both compose configs render with AI env on backend/worker only; `git diff --check` 0.
- CI: `gh pr checks 6` all SUCCESS on HEAD `97cb4ed` (push run 35531122080 and pull_request run 35531125281): backend-pytest, backend-quantlib-hard-gate, frontend-test-build, lint-static-analysis, e2e-playwright, postgres-persistence-smoke, PR-FAST, PR-FULL. Mergeable/CLEAN vs `cursor/openai-risk-assistant`. Normal CI does not set `RUN_LIVE_AI_TESTS`.

---

## Post-review corrective queue

External review of HEAD `b70fccd` found merge-blocking gaps in continuation policy, production conversation routing, grounding semantics, and hard budget enforcement. Previous green evidence is baseline evidence only.

Execution order: **C13 → C14 → C15 → C16 → C17 → C18 → C19 → C12**.

For every task below, the root agent must:

- work only the first eligible unchecked task;
- inspect current HEAD before editing;
- delegate only non-overlapping paths;
- add a regression test that fails on `b70fccd` and passes after the fix;
- record the exact commit SHA and fresh command output;
- commit, push, and stop after that one task.

## C13 — Preserve policy on every Responses continuation

- [x] Keep the security and grounding policy active after `function_call_output`.

Dependencies: C04

Primary owner: openai-loop  
Read-only reviewer: security-grounding

Write scope: `backend/app/ai/policy.py`, `request_builder.py`, `openai_model.py` only if required, and focused tests.

Acceptance:

- Every `responses.create`, including calls using `previous_response_id`, supplies a versioned instruction.
- Use distinct routing and narration instructions if needed.
- Narration may restate deterministic tool facts, but may not calculate, invent, advise, disclose secrets, or follow instructions embedded in tool output.
- Tool output is explicitly treated as untrusted data.
- Replace the existing test asserting continuation instructions are absent.
- Add a malicious tool-output test containing prompt injection and sentinel secrets.
- No client receives provider prompts or secrets.

Checks:

```bash
cd backend
python3 -m pytest tests/test_openai_request_builder.py tests/test_openai_model.py tests/test_ai_security.py -q
ruff check app/ai tests/test_openai_request_builder.py tests/test_openai_model.py tests/test_ai_security.py
```

Evidence:

- Product HEAD: `028a49d` (`fix: send versioned policy on every Responses continuation (C13)`). `backend/app/ai/policy.py` v**1.1.0** adds distinct `ROUTING_POLICY_INSTRUCTION` and `NARRATION_POLICY_INSTRUCTION`. `build_openai_continue_request` now sets `instructions` on every `previous_response_id` continue (routing while tools may still be selected; narration when `reserve_narration=True`). Tool output remains untrusted data in both texts. `openai_model.py` unchanged (uses the builder).
- Replaced `assert "instructions" not in payload.create_params` in `test_continue_request_appends_function_call_outputs`. Added malicious tool-output tests with prompt injection and sentinels (`sk-sentinel-tool-inject-c13-*`, `QL_INTERNAL_PROMPT_C13*`). Client dumps must not contain policy text or planted secrets.
- Security-grounding reviewer (read-only): continue omitted `instructions` at `request_builder.py` create_params; only routing policy existed; no active client prompt leak found. Root implemented under TDD.
- Regression vs `b70fccd`: restoring that commit's `policy.py` / `request_builder.py` fails the four continue-instruction tests with `KeyError: 'instructions'` (4 failed). After the fix they pass.
- Checks (2026-09-21, Python 3.12.3), fresh:
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_openai_request_builder.py tests/test_openai_model.py tests/test_ai_security.py -q
  ruff check app/ai tests/test_openai_request_builder.py tests/test_openai_model.py tests/test_ai_security.py
  ```
  → **65 passed**, 1 warning, exit **0** (2.97s). ruff: All checks passed.

Next eligible after this commit: **C14**. Do not start it in this run. C12 stays open until C13–C19 finish.

## C14 — Enforce hard model-turn and tool-call budgets

- [x] Make configured budgets true upper bounds and remove exception-driven replay.

Dependencies: C13

Primary owner: orchestration  
Read-only reviewer: openai-loop

Write scope: `backend/app/ai/assistant.py`, `config.py` if validation changes, and bounded-loop/config tests.

Acceptance:

- Total provider calls never exceed `AI_MAX_TOOL_ROUNDS`; reserved narration counts toward the limit.
- Executed tools never exceed `AI_MAX_TOOL_CALLS`.
- Conversational configuration requires enough turns for route/tool/narration or fails clearly; no hidden `+1` call.
- Remove the broad `except TypeError` compatibility retry around `continue_after_tools`.
- A `TypeError` inside the adapter produces one invocation only and follows the typed failure path.
- Already-executed tools are never replayed.
- Tests assert exact provider/tool counts at limits 1–4.

Checks:

```bash
cd backend
python3 -m pytest tests/test_ai_bounded_assistant.py tests/test_ai_bounded_http.py tests/test_ai_config.py tests/test_openai_model.py -q
```

Evidence:

- Product HEAD: `b8b371c` (`fix: enforce hard model-turn budget without hidden extra continue (C14)`). `BoundedRiskAssistant.run` loops `range(1, max_model_turns + 1)` only. A tool on the last model turn does not execute (no hidden continue to send `function_call_output`). After an executed tool, the next continue is reserved when the tool budget is exhausted **or** the next round is the last model turn. `rounds_used` is never `max_model_turns + 1`.
- `continue_after_tools` `TypeError` is converted to `OpenAIModelParseError` with no retry. HTTP already maps that after executed tools to truncated fallback without replay (`test_continue_type_error_after_tool_is_partial_fallback_without_replay`).
- Conversational `get_ai_settings` fails when `max_tool_rounds < max_tool_calls + 1`. Router may use `AI_MAX_TOOL_ROUNDS=1`. `test_max_tool_rounds_allows_one_through_four` sets router for rounds=1.
- Exact provider/tool counts at limits 1–4: provider calls == `max_rounds`; tools == `max(max_rounds - 1, 0)`. Cap-at-four is 4 provider calls / 3 tools, not 5/4. `test_final_tool_turn_*` uses `max_rounds=2`.
- `mt-safe-02` no longer expects two executed tools under `max_rounds=2` (that encoded the hidden +1).
- Checks (2026-09-21, Python 3.12.3), fresh:
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_ai_bounded_assistant.py tests/test_ai_bounded_http.py tests/test_ai_config.py tests/test_openai_model.py -q
  ruff check app/ai/assistant.py app/ai/config.py tests/test_ai_bounded_assistant.py tests/test_ai_bounded_http.py tests/test_ai_config.py tests/test_ai_multi_tool_evals.py
  ```
  → **87 passed**, exit **0** (2.47s) for the C14 suite; related AI evals including `test_ai_multi_tool_evals.py` also green (**189 passed** across the combined related run). ruff: All checks passed.

Next eligible after this commit: **C15**. Do not start C12 until C13–C19 finish.

## C15 — Make quantitative grounding fail closed

- [x] Require the correct metric, unit, and sign convention for every numeric claim.

Dependencies: C13, C14

Primary owner: security-grounding  
Read-only reviewer: quant-tools

Write scope: `backend/app/ai/narration.py` and grounding/security/evaluation tests.

Acceptance:

- An unclassified numeric phrase cannot match an arbitrary financial value.
- Counts, ids, dates, years, confidence values, and unrelated metadata cannot ground financial claims.
- Preserve sign unless the manifest explicitly defines an absolute-loss display convention.
- Currency, percent, ratio, per-bp, and Greek units cannot cross-ground.
- Equal values belonging to different metrics cannot cross-ground.
- Reject at least: payload `VaR=100` with narration `100 positions`; payload `loss=-100` with narration `profit 100`; VaR/delta value collisions; ratio/percent/currency collisions.
- Rejected prose uses deterministic formatting and never reports `narration_grounded=true`.

Checks:

```bash
cd backend
python3 -m pytest tests/test_ai_narration_grounding.py tests/test_ai_security.py tests/test_ai_conversational_evals.py -q
```

Evidence:

- Product HEAD: `fb9a3cf` (`fix: fail-closed quantitative narration grounding (C15)`). `_metric_compatible` no longer treats unclassified numeric phrases as matching any financial claim. `_value_matches` preserves sign unless `sign_convention` is an absolute-loss display convention. Deterministic fallback strips `not on this payload` so rejected narration cannot leak that placeholder into user prose. `narration_grounded` remains false on rejection (existing bounded-assistant fallback test).
- Attacks covered: `100 positions` vs VaR=100; `profit 100` and unsigned `loss 100` vs `worst_loss=-100`; VaR/delta collisions; ratio/percent/currency collisions; unclassified confidence `0.99`.
- Checks (2026-09-21, Python 3.12.3), fresh:
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_ai_narration_grounding.py tests/test_ai_security.py tests/test_ai_conversational_evals.py -q
  ruff check app/ai/narration.py tests/test_ai_narration_grounding.py tests/test_ai_conversational_evals.py
  ```
  → **101 passed**, 1 warning, exit **0** (1.93s). ruff: All checks passed.

Next eligible after this commit: **C16**. Do not start C12 until C13–C19 finish.

## C16 — Make two-turn chat work in the shipped Compose topology

- [x] Remove the split between synchronous chat and external-worker fallback.

Dependencies: C14

Primary owner: conversation-state  
Read-only reviewers: architecture-auditor and frontend-chat  
Integration hotspot owner: root

Acceptance:

- With normal Compose `QUANTLINEAGE_EXTERNAL_WORKER=1`, two consecutive Risk Query turns succeed.
- Choose exactly one production path: keep `/risk/query` interactive with workload limits, or support `conversation_id` through typed RiskRun requests plus shared persistent conversation state.
- The frontend must never send `conversation_id` to a schema that rejects it.
- If workers execute chat, state and ownership must work across processes; process-local memory is insufficient.
- Cross-principal access fails closed.
- Add a Compose-shaped first-turn → returned-id → follow-up test.
- No OpenAI key reaches frontend or RiskRun payloads.

Checks:

```bash
cd backend
python3 -m pytest tests/test_ai_conversations.py tests/test_ai_bounded_http.py tests/test_api_typed_models.py -q
cd ..
docker compose -f docker-compose.yml config
POSTGRES_PASSWORD=dummy-ci QUANTLINEAGE_API_TOKEN=dummy-token docker compose -f docker-compose.shared.yml config
```

Evidence:

- Product HEAD: `893c47a` (`fix: keep Risk Query interactive in Compose worker topology (C16)`). Chose the interactive production path: `POST /risk/query` is no longer `reject_inline_heavy`. Workload caps still apply via `enforce_workload_limits`. Chat is not a worker job; in-memory conversation state stays in the API process. `askRisk` posts only to `/risk/query` and does not fall back to `QueryRiskRunRequest` (which `extra=forbid` rejects `conversation_id`). Cross-principal denial remains in `test_cross_principal_conversation_access_fails_closed`. Compose-shaped HTTP test: first turn returns `conv_*`, follow-up reuses it under `QUANTLINEAGE_EXTERNAL_WORKER=1`.
- Frontend vitest `src/api.test.js` + `src/components/RiskQuery.test.jsx` → **36 passed**. Browser UI not exercised (no `/tmp/cursor/start-user` services).
- Checks (2026-09-21, Python 3.12.3), fresh:
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_ai_conversations.py tests/test_ai_bounded_http.py tests/test_api_typed_models.py -q
  docker compose -f docker-compose.yml config
  POSTGRES_PASSWORD=dummy-ci QUANTLINEAGE_API_TOKEN=dummy-token docker compose -f docker-compose.shared.yml config
  ```
  → **48 passed**, 1 warning, exit **0** (2.30s). Both compose configs render.

Next eligible after this commit: **C17**. Do not start C12 until C13–C19 finish.

## C17 — Store useful bounded context and reclaim expired state

- [x] Make conversation state a real bounded transcript with bounded storage.

Dependencies: C16

Primary owner: conversation-state  
Read-only reviewer: security-grounding

Acceptance:

- Model context is chronological: prior user turn, prior assistant answer, relevant tool identity/arguments, then current question.
- Follow-ups can refer to the answer the user saw without provider ids, prompts, chain-of-thought, secrets, or unbounded tool JSON.
- Enforce a context byte/token cap as well as the turn cap.
- Reclaim expired records without requiring a later lookup of that id.
- Add a global or per-principal capacity bound with deterministic eviction.
- Concurrent access remains ownership-safe.
- Test clarification follow-up, reference to prior answer, expiry sweep, capacity eviction, and cross-principal denial.

Checks:

```bash
cd backend
python3 -m pytest tests/test_ai_conversations.py tests/test_ai_provider_integration.py tests/test_ai_security.py -q
```

Evidence:

- Product HEAD: `7d435ab` (`fix: bound conversation context, expiry sweep, and capacity (C17)`). `conversation_history_for_model` emits question → answer → tool identity/args (no `tool_result`, no provider ids). Context is capped at `CONVERSATION_MAX_CONTEXT_BYTES` (2048) in addition to 8 turns. `reclaim_expired()` sweeps TTL without looking up that id (also on create/get/append). Per-principal `CONVERSATION_MAX_PER_PRINCIPAL` evicts oldest `updated_at`. OpenAI request input is chronological prior turns then current question. Concurrent cross-principal access stays fail-closed.
- Checks (2026-09-21, Python 3.12.3), fresh:
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_ai_conversations.py tests/test_ai_provider_integration.py tests/test_ai_security.py -q
  ruff check app/ai/conversations.py app/ai/request_builder.py tests/test_ai_conversations.py tests/test_openai_request_builder.py
  ```
  → **50 passed**, 1 warning, exit **0** (1.55s). ruff: All checks passed.

Next eligible after this commit: **C18**. Do not start C12 until C13–C19 finish.

## C18 — Report the actual Greek pricing engine

- [x] Distinguish wrappers from the deterministic pricing engine/model.

Dependencies: C15

Primary owner: quant-tools  
Read-only reviewer: architecture-auditor

Acceptance:

- Default cached QuantLib configuration identifies `QuantLibPricingEngine`, not only `CachedPricingEngine`.
- Expose wrapper/cache identity separately if useful.
- Builtin pricing identifies `BuiltinPricingEngine`.
- Do not expose raw QuantLib objects.
- Result and provenance retain units, scale, ranking basis, `options_only`, and underlying engine identity.
- Add cached-QuantLib and builtin regression tests.

Checks:

```bash
cd backend
python3 -m pytest tests/test_position_greeks_tool.py tests/test_ai_bounded_http.py tests/test_api_typed_models.py -q
```

Evidence:

- Product HEAD: `8673895` (`fix: report underlying Greek pricing engine behind the cache (C18)`). `report_pricing_engine_identity` unwraps `CachedPricingEngine.inner`. Greeks reports set `pricing_engine`/`pricing_model` to `QuantLibPricingEngine` or `BuiltinPricingEngine` and `pricing_wrapper` to `CachedPricingEngine` when cached. Payload remains JSON-safe (no `ql.` objects). Units, scale, ranking_basis, and options_only are unchanged.
- Checks (2026-09-21, Python 3.12.3), fresh:
  ```
  cd /workspace/backend
  python3 -m pytest tests/test_position_greeks_tool.py tests/test_ai_bounded_http.py tests/test_api_typed_models.py -q
  ruff check app/pricing/cache.py app/services/portfolio_service.py tests/test_position_greeks_tool.py
  ```
  → **52 passed**, 1 warning, exit **0** (2.17s). ruff: All checks passed.

Next eligible after this commit: **C19**. Do not start C12 until C13–C19 finish.

## C19 — Add production-path and regression gates

- [ ] Prove every post-review failure remains fixed before C12.

Dependencies: C13–C18

Primary owner: qa-integrator  
Read-only reviewers: security-grounding, conversation-state, frontend-chat

Acceptance:

- Add one network-free regression for every C13–C18 finding.
- Add a production-shaped two-turn browser/API test using Compose heavy/worker flags.
- Verify continuation policy, malicious tool-output resistance, exact budgets, and no duplicate request after internal `TypeError`.
- Verify count, sign-flip, metric-collision, and unit-collision prose falls back deterministically.
- Verify frontend retry does not duplicate a failed user message in the visible transcript.
- Run focused backend, frontend, and Playwright suites without OpenAI network access.

Checks:

```bash
cd backend
python3 -m pytest tests/test_ai_conversational_evals.py tests/test_ai_security.py tests/test_ai_conversations.py tests/test_ai_bounded_assistant.py tests/test_ai_bounded_http.py -q
cd ../frontend
npm test -- --run src/components/RiskQuery.test.jsx
npm run lint
npm run build
cd ../e2e
npx playwright test tests/risk-query.spec.ts
```

Completion note:

- After C19, run C12 on the new final HEAD.
- The opt-in live OpenAI smoke must actually succeed. Without an authorized key, mark C12 `[!]` and stop; a skipped test is not passing evidence.
- Run `mypy app` exactly as documented. If policy permits a known baseline, record the full comparison and prove zero new findings in every changed file; do not report `mypy app/ai` as equivalent.

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
