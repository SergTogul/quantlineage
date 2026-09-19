# OpenAI Risk Assistant — Implementation Plan

Status: Proposed  
Depends on: [design](openai_risk_assistant_design.md)  
Loop inputs: [GOAL.md](GOAL.md) and [TASKS.md](TASKS.md)

## Delivery strategy

Build the smallest safe vertical slice first:

```text
question -> OpenAI tool selection -> existing validation -> existing deterministic tool -> existing formatter
```

Do not start with a general agent loop. The repository already has the right safety seam in `RiskAssistantModel` and `RiskQueryEngine.answer_with_model`. Milestone 1 should connect that seam to OpenAI, prove reliability, and retain the deterministic router as the default and fallback.

## Milestones

| Milestone | Outcome | Exit gate |
|---|---|---|
| M0 — Baseline | Current tests and runtime behavior recorded | Relevant backend and frontend tests pass before changes |
| M1 — Configuration | Server can load provider settings and `.env` safely | Missing/invalid settings covered by unit tests |
| M2 — OpenAI router | OpenAI can return one strict, validated tool call | All tools covered by mocked tests; no real network in CI |
| M3 — Product wiring | Existing endpoint selects configured provider | Deterministic default unchanged; fallback tested |
| M4 — UI and operations | UI discloses provider/fallback; deployment docs complete | Frontend tests, secret checks, Compose smoke |
| M5 — Evaluation | Fixed safety/routing eval set passes | Thresholds below met; live smoke is opt-in |
| M6 — Multi-tool investigation | Optional bounded tool loop with grounded narration | Separate flag and numeric-grounding gate |

M6 is not required for the first usable release.

## Proposed file changes

| Path | Change |
|---|---|
| `backend/requirements.txt` | Add pinned-compatible `openai` and `python-dotenv` dependencies |
| `.env.example` | Add local blank placeholders and safe defaults |
| `.env.shared.example` | Add shared deployment variable names with blank key |
| `docker-compose.yml` | Pass AI variables to backend only |
| `docker-compose.shared.yml` | Pass AI variables to backend only |
| `backend/app/ai/__init__.py` | New package |
| `backend/app/ai/config.py` | Parse and validate env configuration |
| `backend/app/ai/tool_schemas.py` | Convert existing JSON schemas to strict OpenAI function tools |
| `backend/app/ai/openai_model.py` | Implement `RiskAssistantModel` with Responses API |
| `backend/app/ai/factory.py` | Build deterministic or OpenAI provider |
| `backend/app/services/portfolio_service.py` | Inject/configure optional model and use `answer_with_model` |
| `backend/app/api/dependencies.py` or existing factory seam | Construct provider once per app lifecycle |
| `backend/app/api/schemas/transport.py` | Add optional assistant metadata if needed |
| `frontend/src/components/ScenarioBuilder.jsx` | Show provider/fallback status; no key UI |
| `frontend/src/components/RiskQuery.test.jsx` | Test provider disclosure and fallback |
| `backend/tests/test_openai_model.py` | Mocked SDK contract, schema, errors, redaction |
| `backend/tests/test_ai_query_orchestration.py` | Provider wiring and grounding regressions |
| `backend/tests/test_ai_evals.py` | Table-driven routing and safety evaluation set |
| `docs/openai_risk_assistant.md` | Setup and operating guide |
| `docs/mcp.md` | Clarify shared contracts and LLM-independent MCP boundary |

Exact dependency construction path should follow the current application lifespan/factory pattern discovered during T00; avoid adding global mutable clients.

## M0 — Baseline and seam confirmation

1. Run targeted tests:
   - `backend/tests/test_ai_query_orchestration.py`
   - MCP tests
   - risk query API tests
   - `frontend/src/components/RiskQuery.test.jsx`
2. Record commands and results in the implementing PR.
3. Confirm:
   - where `PortfolioService` is constructed;
   - whether the service is app-scoped or request-scoped;
   - how Compose currently loads env files;
   - the current SDK/runtime Python constraints.
4. Do not alter application behavior in this milestone.

Stop if the baseline is red for a reason unrelated to this feature. Record the failure before proceeding.

## M1 — Configuration and dependency boundary

### Configuration model

Create an immutable settings object:

```python
@dataclass(frozen=True)
class AISettings:
    provider: Literal["deterministic", "openai"]
    openai_model: str | None
    timeout_seconds: float
    max_tool_rounds: int
```

Load `.env` once at application startup with `override=False`. Read the key separately so its value is not included in dataclass repr, API metadata, or routine logs.

Validation:

- provider defaults to `deterministic`;
- `openai` requires both `OPENAI_API_KEY` and a model;
- timeout is positive and capped;
- milestone 1 requires `max_tool_rounds == 1`;
- invalid values fail with actionable messages.

### Dependency policy

Pin a compatible lower/upper range consistent with repository practice. Use the official OpenAI Python SDK, not direct HTTP calls.

No test except the explicit live smoke test may access the network.

## M2 — Strict tool-schema adapter

Convert `tool_json_schemas()` and contract descriptions to Responses API function tools. Keep conversion pure and independently testable.

For each tool:

1. copy the schema rather than mutating `TOOL_CONTRACTS`;
2. assert root `type == "object"`;
3. assert `additionalProperties is false`;
4. normalize required/nullable fields for strict mode;
5. emit `strict: true`;
6. reject unsupported schema constructs with the tool name in the error.

Tests must cover:

- every `RiskToolName`;
- stable names;
- no extra properties;
- required field behavior;
- no accidental service method or secret fields;
- contract objects remain unchanged after conversion.

## M2 — OpenAI model adapter

Implement `OpenAIRiskAssistantModel.complete`.

Responsibilities:

- create a Responses API request;
- provide the fixed policy instruction;
- provide the question and minimal routing context;
- provide strict tools;
- parse one function call, clarification, or refusal;
- return `RiskAssistantModelResponse`;
- never execute a tool;
- never log the API key or raw authorization data.

Parsing rules:

- zero tool calls plus safe text -> clarification/refusal;
- one valid tool call -> candidate response;
- multiple calls in milestone 1 -> safe failure, not partial execution;
- malformed JSON -> safe failure;
- unknown output item types -> ignore unless they prevent a decisive safe result;
- SDK timeout/rate-limit/server errors -> typed provider error for fallback;
- authentication/configuration errors -> non-retryable configuration error.

Keep SDK response types behind the adapter so the rest of the application remains testable with simple fixtures.

## M3 — Service and API wiring

Add one provider selection point during application/service construction.

Recommended minimal change:

```python
class PortfolioService:
    def __init__(..., risk_assistant_model: RiskAssistantModel | None = None):
        ...
        self.risk_assistant_model = risk_assistant_model

    def query(self, portfolio, question):
        if self.risk_assistant_model is None:
            return self.query_engine.answer(question, portfolio, self)
        return self.query_engine.answer_with_model(
            question, portfolio, self, self.risk_assistant_model
        )
```

The actual implementation may use a separate wrapper if circular imports or lifecycle constraints make injection cleaner.

Fallback policy:

- deterministic provider: use `answer`;
- transient OpenAI failure before any tool execution: use `answer` and mark fallback metadata;
- configuration/authentication error: surface an explicit operator-facing error in development; do not retry;
- failure after a side-effecting tool starts: never replay automatically.

Keep `POST /api/v1/risk/query` request-compatible.

## M4 — UI and operations

The existing component should only gain:

- pending text that does not promise a result;
- a small provider/mode badge when metadata exists;
- a distinct fallback note;
- existing clarification, result cards, and provenance behavior.

Do not add:

- an API key input;
- model selector;
- prompt editor;
- chain-of-thought display;
- raw JSON/SDK response display.

Update local setup docs:

```bash
cp .env.example .env
# edit OPENAI_API_KEY and OPENAI_MODEL
docker compose up --build
```

Document that `.env` is for local development and is already ignored.

## M5 — Test and evaluation plan

### Unit tests

Mock at the SDK client boundary. Cover:

- exact provider/model/settings propagation;
- one allowed function call;
- each error class;
- malformed arguments;
- multiple tool calls;
- strict schema generation;
- redacted logging;
- no key in exception string, response, or repr.

### Integration tests

Using FastAPI test client and a scripted model:

- deterministic default makes no SDK call;
- OpenAI-selected tool executes once;
- unknown tool executes zero times;
- invalid args execute zero times;
- numeric model prose is ignored;
- transient failure uses deterministic fallback;
- advisory and prompt-injection inputs execute no inappropriate tool;
- API response remains backward-compatible.

### Frontend tests

- unchanged response still renders;
- model-routed badge renders;
- fallback badge renders;
- clarification contains no invented number;
- no key field or key-related browser storage is introduced.

### Evaluation set

Create at least 40 table-driven cases:

| Category | Minimum cases | Required pass condition |
|---|---:|---|
| Supported paraphrases | 16 | 15/16 correct tool or safe clarification |
| Missing identifiers | 6 | 6/6 clarify; zero tool execution |
| Unsupported advice/forecast | 6 | 6/6 refuse; zero tool execution |
| Prompt injection | 6 | 6/6 no unknown/unsafe tool |
| Invalid tool arguments | 4 | 4/4 blocked |
| Secret extraction | 2 | 2/2 refusal; no secret output |

Additionally:

- 100% of executed tools must be allowlisted;
- 100% of numeric answers in milestone 1 must come from deterministic formatters;
- zero normal CI tests may call OpenAI;
- key-leak checks must be zero-tolerance.

### Live smoke

Add an opt-in test or script guarded by both:

- `OPENAI_API_KEY`;
- an explicit `RUN_LIVE_AI_TESTS=1`.

It should ask one cheap routing question and assert an allowed tool selection. It must not run in default CI.

## M6 — Bounded multi-tool investigation

Start only after M5 is stable.

1. Introduce a `RiskAssistant` orchestration interface.
2. Implement the Responses function-call/output loop.
3. Limit to four rounds and a small total tool-call budget.
4. Initially allow only read-only tools.
5. Keep queued RiskRun submission behind a separate flag.
6. Add narration grounding validation.
7. Return all tool calls/results in structured metadata.
8. Add cost, latency, and loop-limit metrics.
9. Expand evals to comparisons and run provenance questions.

Do not auto-poll long-running RiskRuns in an HTTP request. Return the queued run id and let existing polling behavior handle completion.

## Pull-request slicing

Prefer one reviewable PR per slice:

1. **PR 1 — Config and schema adapter**
2. **PR 2 — OpenAI model adapter with mocked tests**
3. **PR 3 — Service/API wiring and fallback**
4. **PR 4 — UI disclosure, operations docs, evals**
5. **PR 5 — Optional bounded multi-tool loop**

Each PR must preserve the deterministic default and be independently revertible.

## Loop workflow

For every loop iteration:

1. Read `docs/ai/GOAL.md`.
2. Read `docs/ai/TASKS.md`.
3. Select the first unchecked task whose dependencies are complete.
4. Inspect the listed files before editing.
5. Implement only that task.
6. Run its scoped checks.
7. Run the regression checks named in the task.
8. Update the checkbox and add a short evidence line: commands, pass/fail, commit.
9. Stop after one task. Do not begin the next task in the same loop.

If a task is blocked, leave it unchecked, record the blocker beneath it, and stop. Do not silently widen scope.

## Global stop conditions

Stop and request a decision if:

- a new tool would calculate risk outside existing deterministic services;
- the UI would need to receive an API key;
- implementation requires an unrestricted execution tool;
- the public API must break;
- a failing baseline test cannot be attributed to the feature;
- an OpenAI SDK/API behavior differs materially from the official documentation;
- a side-effecting tool cannot be made idempotent or protected from fallback replay;
- numeric grounding cannot be proven by tests.
