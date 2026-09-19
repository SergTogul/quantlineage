# OpenAI Risk Assistant — Operator Guide

Server-side optional routing for `POST /api/v1/risk/query`. The model selects
one allowlisted tool; deterministic formatters remain authoritative for numbers.
No API key, model selector, or prompt editor exists in the frontend.

## Default behavior

`QUANTLINEAGE_AI_PROVIDER` defaults to **`deterministic`**. In this mode:

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
   QUANTLINEAGE_AI_PROVIDER=openai
   QUANTLINEAGE_OPENAI_MODEL=<model-id>
   ```

3. Start the stack (Compose reads `.env` for backend/worker substitution):

   ```bash
   docker compose up --build
   ```

The backend also calls `load_dotenv(override=False)` on startup, so a local
`.env` works for non-Compose runs as well. Exported shell variables win over
`.env` file values.

### Optional tuning

| Variable | Default | Notes |
|---|---|---|
| `QUANTLINEAGE_AI_TIMEOUT_SECONDS` | `30` | Max `120` |
| `QUANTLINEAGE_AI_MAX_OUTPUT_TOKENS` | `512` | Max `4096` |
| `QUANTLINEAGE_AI_MAX_TOOL_ROUNDS` | `1` | Milestone 1: must stay `1` |

## Shared / production

Use `docker-compose.shared.yml` with `.env.shared` (see `.env.shared.example`)
or inject the same variables through your platform secret manager. **Do not**
place `OPENAI_API_KEY` in frontend build args, `VITE_*` variables, or browser
storage. Only `backend` and `worker` services receive AI environment variables.

Recommended practice:

- Store `OPENAI_API_KEY` in the deployment platform's secret store.
- Keep `QUANTLINEAGE_AI_PROVIDER=deterministic` until routing evals pass in
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
| Failure after a side-effecting tool starts | No automatic replay |

The UI shows a subtle **AI-routed** label when metadata indicates model routing,
and a **Deterministic fallback** note when fallback metadata is present.

## Cost controls

Milestone 1 limits spend by design:

- One model round and at most one tool call per query.
- Bounded timeout and output token cap (see table above).
- No conversation history or automatic RiskRun polling in the query path.
- Default provider is deterministic (zero OpenAI cost).

Monitor OpenAI usage in your provider dashboard when enabled.

## Rollback

Disable OpenAI without code changes:

```dotenv
QUANTLINEAGE_AI_PROVIDER=deterministic
```

Restart backend (and worker if running). Remove or leave `OPENAI_API_KEY` unset;
deterministic mode ignores it. Behavior returns to the pre-OpenAI routing path.

## Boundaries

- **Frontend:** displays optional assistant metadata only; no secrets.
- **MCP:** allowlisted deterministic tools only — see [`docs/mcp.md`](mcp.md).
- **Tests:** normal CI is network-free; no live OpenAI calls.

Design and task queue: [`docs/ai/openai_risk_assistant_design.md`](ai/openai_risk_assistant_design.md),
[`docs/ai/TASKS.md`](ai/TASKS.md).
