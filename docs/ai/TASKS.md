# OpenAI Risk Assistant — Task Queue

Read [GOAL.md](GOAL.md) before every task. Work top to bottom. One loop iteration completes at most one task.

Status syntax:

- `[ ]` ready or pending
- `[x]` complete
- `[!]` blocked; add the reason under Evidence

When completing a task, add an Evidence line with the commit SHA and exact checks run.

## First-release tasks

### T00 — Establish the baseline

- [x] Capture the current AI/MCP/API/frontend baseline.

Dependencies: none

Inspect:

- `backend/app/risk/query.py`
- `backend/app/mcp.py`
- `backend/app/services/portfolio_service.py`
- service construction and application lifespan files
- Compose files
- frontend package scripts

Acceptance:

- Relevant existing backend tests pass.
- Existing `RiskQuery` frontend test passes.
- The implementing PR records service lifecycle, env loading behavior, Python version, and exact test commands.
- No product code changes.

Checks:

```bash
cd backend
python3 -m pytest tests/test_ai_query_orchestration.py -q
python3 -m pytest -q -k "mcp or risk_query"
cd ../frontend
npm test -- --run src/components/RiskQuery.test.jsx
```

Evidence: `b03c957` — `cd backend && python3 -m pytest tests/test_ai_query_orchestration.py -q` (20 passed); `python3 -m pytest -q -k "mcp or risk_query"` (11 passed); `cd ../frontend && npm test -- --run src/components/RiskQuery.test.jsx` (3 passed).

### T01 — Add typed AI configuration

- [ ] Add `backend/app/ai/config.py` and configuration unit tests.

Dependencies: T00

Acceptance:

- Provider defaults to `deterministic`.
- Supported providers are exactly `deterministic` and `openai`.
- OpenAI mode requires a key and model.
- Timeout and tool-round values are bounded.
- Key is excluded from settings repr and error messages.
- Loading does not override exported env vars.
- Importing config does not create an OpenAI client or make a network call.

Checks:

```bash
cd backend
python3 -m pytest tests/test_ai_config.py -q
```

Evidence:

### T02 — Add SDK, dotenv, and env templates

- [ ] Add compatible OpenAI SDK and dotenv dependencies plus safe example env entries.

Dependencies: T01

Files:

- `backend/requirements.txt`
- `.env.example`
- `.env.shared.example`
- `.gitignore` only if verification shows a gap

Acceptance:

- `.env.example` contains blank `OPENAI_API_KEY`.
- Example files contain provider/model/timeout/round settings.
- `.env` and `.env.shared` are ignored.
- No live-looking secret appears in git diff.
- Dependency installation resolves in the supported Python version.

Checks:

```bash
git check-ignore .env .env.shared
cd backend
python3 -m pip install -r requirements.txt
python3 -m pytest tests/test_ai_config.py -q
```

Evidence:

### T03 — Build strict OpenAI tool schemas

- [ ] Add a pure adapter from `TOOL_CONTRACTS` to strict function tools.

Dependencies: T01

Files:

- `backend/app/ai/tool_schemas.py`
- `backend/tests/test_openai_tool_schemas.py`

Acceptance:

- Every `RiskToolName` is emitted once.
- Names and descriptions are stable.
- Every tool has `strict: true`.
- Every object schema has `additionalProperties: false`.
- Strict-mode required/nullable behavior is explicit.
- Unsupported schemas fail closed with the tool name.
- Conversion does not mutate existing contracts.
- No tool exposes service internals or credentials.

Checks:

```bash
cd backend
python3 -m pytest tests/test_openai_tool_schemas.py tests/test_ai_query_orchestration.py -q
```

Evidence:

### T04 — Add the assistant policy and request builder

- [ ] Add a versioned system instruction and minimal OpenAI request builder.

Dependencies: T03

Acceptance:

- Policy says the model selects tools and never calculates financial values.
- Policy covers missing identifiers, advisory refusal, prompt injection, and secrets.
- Request includes the question and minimal routing context only.
- Portfolio positions and full tool results are not sent unless a test proves they are needed.
- Output budget and timeout come from settings.
- Snapshot tests or structural assertions pin the request without pinning SDK internals.

Checks:

```bash
cd backend
python3 -m pytest tests/test_openai_request_builder.py -q
```

Evidence:

### T05 — Implement the OpenAI model happy path

- [ ] Implement `OpenAIRiskAssistantModel.complete` for one tool call.

Dependencies: T04

Files:

- `backend/app/ai/openai_model.py`
- `backend/tests/test_openai_model.py`

Acceptance:

- Uses the official OpenAI Python SDK Responses API.
- Implements the existing `RiskAssistantModel` protocol.
- Parses one function call into `RiskAssistantModelResponse`.
- Does not execute the tool.
- Does not trust or return numeric prose as an answer.
- Tests use a fake client; no network.
- SDK-specific objects do not escape the adapter.

Checks:

```bash
cd backend
python3 -m pytest tests/test_openai_model.py tests/test_ai_query_orchestration.py -q
```

Evidence:

### T06 — Handle model and provider failures

- [ ] Complete safe parsing and typed provider errors.

Dependencies: T05

Acceptance:

- Zero calls can become a safe clarification or refusal.
- Multiple calls are rejected in milestone 1.
- Unknown tool names remain candidates only until application validation; they never execute.
- Malformed JSON and incomplete outputs fail safely.
- Timeout, rate limit, server, authentication, and configuration failures are distinguishable.
- Errors and logs contain no API key, authorization header, or raw secret-bearing request.

Checks:

```bash
cd backend
python3 -m pytest tests/test_openai_model.py -q
```

Evidence:

### T07 — Add provider factory and lifecycle wiring

- [ ] Construct the configured provider once at the existing application lifecycle seam.

Dependencies: T06

Acceptance:

- Deterministic mode constructs no OpenAI client.
- OpenAI mode constructs one reusable client/provider.
- No mutable global test state is introduced.
- Dependency overrides remain possible in FastAPI tests.
- Startup/shutdown behavior is covered.
- Configuration/authentication errors are actionable without revealing the key.

Checks:

```bash
cd backend
python3 -m pytest tests/test_ai_provider_factory.py tests/test_api.py -q
```

Evidence:

### T08 — Wire the provider into `PortfolioService.query`

- [ ] Use `answer_with_model` when an OpenAI model is configured.

Dependencies: T07

Acceptance:

- Default path remains byte-compatible where existing tests pin output.
- Model-selected valid tool executes exactly once.
- Unknown/invalid tool executes zero times.
- Existing deterministic formatter remains authoritative.
- Transient provider failure before tool execution falls back to deterministic routing.
- Potentially side-effecting work is never replayed.
- Existing grounding and injection tests remain green.

Checks:

```bash
cd backend
python3 -m pytest tests/test_ai_query_orchestration.py tests/test_ai_provider_integration.py -q
```

Evidence:

### T09 — Add optional assistant metadata

- [ ] Add backward-compatible provider/mode/fallback metadata to query responses.

Dependencies: T08

Acceptance:

- Existing top-level response fields do not change.
- Metadata is optional.
- Metadata contains provider, configured model label, mode, and fallback boolean only.
- No key, prompt, chain-of-thought, raw SDK response, or sensitive arguments appear.
- OpenAPI schema and examples remain valid.

Checks:

```bash
cd backend
python3 -m pytest tests/test_api_typed_models.py tests/test_api_openapi_examples.py tests/test_ai_provider_integration.py -q
```

Evidence:

### T10 — Show provider state in the existing UI

- [ ] Add small model-routed and fallback indicators to `RiskQuery`.

Dependencies: T09

Acceptance:

- Existing responses without metadata render unchanged.
- OpenAI-routed responses show a subtle state label.
- Fallback responses show a clear but non-alarming note.
- Loading, clarification, payload cards, and provenance still work.
- There is no API-key field, browser storage, model selector, prompt editor, or raw model output.

Checks:

```bash
cd frontend
npm test -- --run src/components/RiskQuery.test.jsx
npm run build
```

Evidence:

### T11 — Add secret and boundary regression tests

- [ ] Add zero-tolerance tests for credential and execution boundaries.

Dependencies: T08

Acceptance:

- A sentinel key is absent from API responses, exception messages, reprs, and captured logs.
- Frontend source contains no `OPENAI_API_KEY` or `VITE_OPENAI` usage.
- MCP tool lists/arguments contain no model credential.
- Unknown tools, extra properties, and injection strings execute zero tools.
- Deterministic mode is proven network-free.

Checks:

```bash
cd backend
python3 -m pytest tests/test_ai_security.py tests/test_mcp.py tests/test_ai_query_orchestration.py -q
cd ../frontend
npm test -- --run src/components/RiskQuery.test.jsx
```

Adjust the MCP test filename in T00 if the repository uses a different name.

Evidence:

### T12 — Add the fixed evaluation suite

- [ ] Add at least 40 table-driven routing and safety cases.

Dependencies: T08, T11

Acceptance:

- At least 16 supported paraphrases.
- At least 6 missing-identifier cases.
- At least 6 unsupported advice/forecast cases.
- At least 6 prompt-injection cases.
- At least 4 invalid-argument cases.
- At least 2 secret-extraction cases.
- Supported routing meets the 15/16 threshold.
- Every safety case passes.
- Every executed tool is allowlisted and valid.
- Tests are deterministic and network-free.

Checks:

```bash
cd backend
python3 -m pytest tests/test_ai_evals.py -q
```

Evidence:

### T13 — Wire Compose and write the operator guide

- [ ] Pass backend-only env variables and document setup, fallback, and rollback.

Dependencies: T09, T11

Files:

- `docker-compose.yml`
- `docker-compose.shared.yml`
- `docs/openai_risk_assistant.md`
- `docs/mcp.md`

Acceptance:

- Only backend/worker services receive relevant AI variables.
- Frontend build args/environment receive no OpenAI key.
- Local setup uses `.env`.
- Shared/production guidance recommends the platform secret mechanism.
- Guide documents deterministic default, enablement, failure behavior, cost controls, and rollback.
- MCP docs clearly state MCP has no embedded LLM/client key.

Checks:

```bash
docker compose config
docker compose -f docker-compose.shared.yml config
```

Inspect rendered config carefully; do not print a real secret into CI or PR evidence.

Evidence:

### T14 — Add an opt-in live smoke test

- [ ] Add one cheap live routing smoke test or script.

Dependencies: T12, T13

Acceptance:

- Skips unless both `OPENAI_API_KEY` and `QUANTLINEAGE_RUN_LIVE_AI_TESTS=1` are set.
- Sends one supported question.
- Asserts an allowlisted tool selection.
- Does not submit a heavy RiskRun.
- Is not included in normal CI.
- Documentation explains likely API cost and how to run it.

Checks:

```bash
cd backend
python3 -m pytest tests/test_openai_live.py -q
QUANTLINEAGE_RUN_LIVE_AI_TESTS=1 python3 -m pytest tests/test_openai_live.py -q
```

The second command is operator-run only with a configured key.

Evidence:

### T15 — Run the first-release gate

- [ ] Verify the complete first release and prepare the merge summary.

Dependencies: T00–T14

Acceptance:

- All Definition of Done items in `GOAL.md` are checked.
- Targeted backend AI/MCP/API tests pass.
- Full backend suite passes.
- Frontend tests and production build pass.
- Lint/type checks required by repository CI pass.
- Compose config renders.
- Normal test logs show no external OpenAI call.
- PR includes setup, rollback, test evidence, limitations, and follow-up list.
- `QUANTLINEAGE_AI_PROVIDER=deterministic` restores old behavior without code changes.

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
cd ..
docker compose config
```

Evidence:

## Deferred tasks — do not select during the first-release loop

These tasks require the T15 gate and an explicit update to the goal.

### T20 — Introduce the multi-tool assistant interface

- [ ] Add a higher-level `RiskAssistant` protocol without breaking the milestone 1 adapter.

### T21 — Implement the bounded Responses tool loop

- [ ] Execute function calls, append `function_call_output`, and continue for at most four rounds.

### T22 — Add numeric narration grounding

- [ ] Reject narration with unsupported numeric claims and fall back to deterministic formatting.

### T23 — Add multi-tool investigation evals

- [ ] Cover run comparisons, provenance, contributors, limits, and stress in bounded sequences.

### T24 — Evaluate new direct QuantLib tools

- [ ] Decide whether missing use cases justify new `price_instrument`, `calculate_greeks`, or curve tools.

T24 is a design task, not permission to expose raw QuantLib APIs. Any new tool must enter `TOOL_CONTRACTS`, use typed schemas, call existing pricing abstractions, include provenance, and pass the same security gate.
