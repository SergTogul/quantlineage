# Merge summary — Hosted OpenAI Risk Assistant (first release)

## Setup

```bash
cp .env.example .env
# set OPENAI_API_KEY, AI_PROVIDER=openai, OPENAI_MODEL
docker compose up --build
```

Default remains `AI_PROVIDER=deterministic` (no OpenAI client, no network).

Operator guide: [docs/openai_risk_assistant.md](../openai_risk_assistant.md).

## Rollback

Set `AI_PROVIDER=deterministic` (or unset it). No code change required.

## Test evidence (T15 gate)

| Check | Result |
|---|---|
| Backend full suite | **2000 passed**, 10 skipped |
| Frontend unit tests | **208 passed** |
| Frontend production build | success |
| Frontend eslint | success (`--max-warnings 0`) |
| Backend ruff (`app` + `tests`) | clean |
| Backend mypy (`mypy app`) | No errors under `app/ai/`. Pre-existing 263 `union-attr` findings remain in 3 non-AI files also present without this change set. |
| `tests/test_openai_live.py` (normal CI) | **skipped** (opt-in) |
| Full-suite log OpenAI hosts | none (`api.openai.com` absent) |
| `docker compose config` | renders; AI env on backend/worker only; frontend none |
| `docker compose -f docker-compose.shared.yml config` | renders with dummy shared secrets; same AI placement |

Targeted AI suites (earlier tasks): config, tool schemas, request builder, model, factory, integration, security, evals — green.

## Limitations

- Conversational OpenAI defaults to one executed tool plus reserved narration (`AI_ASSISTANT_LOOP=conversational`, `AI_MAX_TOOL_ROUNDS=2`, `AI_MAX_TOOL_CALLS=1`). Explicit `AI_ASSISTANT_LOOP=router` is one-shot and never `model-narrated`.
- Conversation state is in-memory (24h TTL, 8 turns) and does not survive process restarts.
- Live OpenAI smoke is opt-in only (`RUN_LIVE_AI_TESTS=1` + key). Normal CI makes no OpenAI network call.
- Worker process does not independently construct a separate OpenAI client beyond shared env; interactive query path is lifespan-wired.
- Agent VM used Python 3.12.3; Docker images target 3.13.

## Follow-ups

- Persist conversation state beyond in-memory (24h TTL, max 8 turns) for shared deployments.
- Confirm live smoke against the chosen production model before enabling by default in shared deployments.
- Optional: wire worker-only AI path if workers ever need model routing (currently unused).
