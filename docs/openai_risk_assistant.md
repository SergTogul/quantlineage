# OpenAI Risk Assistant — Operator Guide

Server-side optional routing for `POST /api/v1/risk/query`. The model selects
allowlisted tools; QuantLineage engines remain authoritative for numbers
([ADR 006](adr/006-llm-orchestrates-not-calculates.md),
[ADR 009](adr/009-grounded-conversational-risk-assistant.md)).
No API key, model selector, or prompt editor exists in the frontend.

Official OpenAI references:

- [Function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Conversation state](https://developers.openai.com/api/docs/guides/conversation-state)

## Canonical environment names

Use these names in code, `.env.example`, Compose, and this guide. Do not
introduce `QUANTLINEAGE_AI_*` aliases.

| Variable | Default | Notes |
|---|---|---|
| `AI_PROVIDER` | `deterministic` | `deterministic` or `openai` |
| `OPENAI_MODEL` | unset | Required when `AI_PROVIDER=openai` |
| `OPENAI_API_KEY` | unset | Server-only; required when provider is `openai` |
| `AI_ASSISTANT_LOOP` | `conversational` | See modes below |
| `AI_MAX_TOOL_ROUNDS` | `2` conversational / `1` router | **Model turns** (`complete` + `continue`), `1`–`4` |
| `AI_MAX_TOOL_CALLS` | `1` | **Executed tools** per query, `1`–`4` |
| `AI_TIMEOUT_SECONDS` | `30` | Max `120` |
| `AI_MAX_OUTPUT_TOKENS` | `512` | Max `4096` |

## Conversational vs router

- **`AI_ASSISTANT_LOOP=conversational`** (chat default when OpenAI is enabled):
  the model selects a tool, QuantLineage executes it, the result is sent back
  as Responses `function_call_output`, and a reserved narration turn produces
  grounded prose. Successful grounded answers use `assistant.mode=model-narrated`.
- **`AI_ASSISTANT_LOOP=router`**: explicit one-shot intent router. Tool JSON
  never re-enters the model. Never present this as chat and never label it
  `model-narrated` (`model-routed` only).

`AI_PROVIDER=deterministic` ignores the loop setting and never calls OpenAI.

## Default behavior

`AI_PROVIDER` defaults to **`deterministic`**. In this mode:

- No OpenAI client is constructed at startup.
- No outbound LLM calls are made.
- Routing and answers match the pre-OpenAI deterministic path.

This is the safe default for CI, demos, and production unless you explicitly
enable OpenAI.

## Enable OpenAI (local)

1. Copy the template and edit values (never commit `.env`):

   ```bash
   cp .env.example .env
   ```

2. Set at minimum:

   ```dotenv
   OPENAI_API_KEY=<your-key>
   AI_PROVIDER=openai
   OPENAI_MODEL=<model-id>
   AI_ASSISTANT_LOOP=conversational
   ```

3. Start the stack (Compose reads `.env` for backend/worker substitution):

   ```bash
   docker compose up --build
   ```

The backend also calls `load_dotenv(override=False)` on startup, so a local
`.env` works for non-Compose runs as well. Exported shell variables win over
`.env` file values.

## Conversation retention

The public API uses an application `conversation_id` (not OpenAI
`previous_response_id`). Follow-ups send that id on `POST /api/v1/risk/query`.

- Local/demo and the current shared FastAPI process store conversations
  **in memory**. They do **not** survive process restarts.
- Records expire after 24 hours of inactivity and keep at most 8 turns.
- Ownership is the authenticated principal (or `demo` when unauthenticated).
  Cross-principal access fails closed.
- Stored turns include questions, answers, tool names/args, and structured
  results. They do not store secrets, raw prompts, chain-of-thought, or
  provider response ids.
- **New conversation** in the UI clears local `conversation_id` and transcript.

Shared deployments that need durable chat history must add persistence; this
slice documents in-memory-only retention.

## Shared / production

Use `docker-compose.shared.yml` with `.env.shared` (see `.env.shared.example`)
or inject the same variables through your platform secret manager. **Do not**
place `OPENAI_API_KEY` in frontend build args, `VITE_*` variables, or browser
storage. Only `backend` and `worker` services receive AI environment variables.

Recommended practice:

- Store `OPENAI_API_KEY` in the deployment platform's secret store.
- Keep `AI_PROVIDER=deterministic` until routing evals pass in
  your environment.
- Apply per-principal API rate limits before enabling in a shared deployment.

## Failure and fallback

| Condition | Behavior |
|---|---|
| Provider `deterministic` | No LLM call; existing router |
| OpenAI timeout / transient error **before** tool execution | Deterministic `answer()` with `assistant.mode=fallback` metadata |
| Invalid or unknown tool from model | Safe refusal or clarification; tool not executed |
| Invalid tool arguments | Clarification; tool not executed |
| Configuration error (missing key/model with `openai`) | Actionable startup or request error; key never logged |
| Failure after a tool has executed | Partial investigation; already-run tools are not replayed |

The UI keys badges off `assistant.mode`: **AI-narrated**, **AI-routed**,
**Deterministic fallback**, or **Request refused**.

## Cost controls

- Conversational mode: one tool-selection turn plus reserved narration by default.
- Router mode: one model round and at most one tool call per query.
- Bounded timeout and output token cap (see table above).
- Default provider is deterministic (zero OpenAI cost).

Monitor OpenAI usage in your provider dashboard when enabled.

## Rollback

Disable OpenAI without code changes:

```dotenv
AI_PROVIDER=deterministic
```

Restart backend (and worker if running). Remove or leave `OPENAI_API_KEY` unset;
deterministic mode ignores it. Behavior returns to the pre-OpenAI routing path.

To keep OpenAI but disable chat continuation, set `AI_ASSISTANT_LOOP=router`.

## Live smoke test (opt-in)

`backend/tests/test_openai_live.py` is opt-in. It must not run in normal CI.

**Requirements:**

```dotenv
OPENAI_API_KEY=<your-key>
OPENAI_MODEL=<model-id>
RUN_LIVE_AI_TESTS=1
```

**Run:**

```bash
cd backend
RUN_LIVE_AI_TESTS=1 python3 -m pytest tests/test_openai_live.py -q
```

Without both `OPENAI_API_KEY` and `RUN_LIVE_AI_TESTS=1`, pytest skips
the test. Normal CI does not set the run flag, so pipelines stay network-free.

## Boundaries

- **Frontend:** displays optional assistant metadata only; no secrets.
- **MCP:** allowlisted deterministic tools only — see [`docs/mcp.md`](mcp.md).
- **Tests:** normal CI is network-free; no live OpenAI calls.

Design and task queue: [`docs/ai/openai_risk_assistant_design.md`](ai/openai_risk_assistant_design.md),
[`docs/ai/CONVERSATIONAL_ASSISTANT_TASKS.md`](ai/CONVERSATIONAL_ASSISTANT_TASKS.md),
[`docs/adr/009-grounded-conversational-risk-assistant.md`](adr/009-grounded-conversational-risk-assistant.md).
