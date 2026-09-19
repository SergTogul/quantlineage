# Merge summary — Hosted OpenAI Risk Assistant (first release)

## Setup

```bash
cp .env.example .env
# set OPENAI_API_KEY, QUANTLINEAGE_AI_PROVIDER=openai, QUANTLINEAGE_OPENAI_MODEL
docker compose up --build
```

Default remains `QUANTLINEAGE_AI_PROVIDER=deterministic` (no OpenAI client, no network).

Operator guide: [docs/openai_risk_assistant.md](../openai_risk_assistant.md).

## Rollback

Set `QUANTLINEAGE_AI_PROVIDER=deterministic` (or unset it). No code change required.

## Test evidence (T15 gate)

| Check | Result |
|---|---|
| Backend full suite | **2000 passed**, 10 skipped |
| Frontend unit tests | **208 passed** |
| Frontend production build | success |
| Frontend eslint | success (`--max-warnings 0`) |
| Backend ruff (`app` + `tests`) | clean |
| `tests/test_openai_live.py` (normal CI) | **skipped** (opt-in) |
| Full-suite log OpenAI hosts | none (`api.openai.com` absent) |
| `docker compose config` | renders; AI env on backend/worker only; frontend none |
| `docker compose -f docker-compose.shared.yml config` | renders with dummy shared secrets; same AI placement |

Targeted AI suites (earlier tasks): config, tool schemas, request builder, model, factory, integration, security, evals — green.

## Limitations

- Milestone 1: one tool call per turn; multi-tool narration deferred (T20+).
- Live OpenAI smoke is opt-in only (`QUANTLINEAGE_RUN_LIVE_AI_TESTS=1` + key).
- Worker process does not independently construct a separate OpenAI client beyond shared env; interactive query path is lifespan-wired.
- Agent VM used Python 3.12.3; Docker images target 3.13.

## Follow-ups

- T20–T24 multi-tool investigation loop after evaluation gates pass in production-like conditions.
- Confirm live smoke against the chosen production model before enabling by default in shared deployments.
- Optional: wire worker-only AI path if workers ever need model routing (currently unused).
