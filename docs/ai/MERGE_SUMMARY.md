# Merge summary — Grounded Conversational Risk Assistant (PR #6)

## Setup

```bash
cp .env.example .env
# set OPENAI_API_KEY, AI_PROVIDER=openai, OPENAI_MODEL
docker compose up --build
```

Default remains `AI_PROVIDER=deterministic` (no OpenAI client, no network).
Conversational OpenAI uses `AI_ASSISTANT_LOOP=conversational` (tool + reserved
narration). Explicit one-shot: `AI_ASSISTANT_LOOP=router`.

Operator guide: [docs/openai_risk_assistant.md](../openai_risk_assistant.md).

## Rollback

Set `AI_PROVIDER=deterministic` (or unset it). No code change required.
To keep OpenAI but disable chat continuation, set `AI_ASSISTANT_LOOP=router`.

## Test evidence (C12 merge gate)

Recorded after the live-smoke update `a5d3337` on
`cursor/risk-query-incomplete-fallback-bebd`. Base
`cursor/openai-risk-assistant` is `0b6a4dc` (also the merge-base; no rebase
required). Python 3.12.3.

| Check | Result |
|---|---|
| Backend full suite | **2158 passed**, 10 skipped, 1 warning (32.97s) |
| Frontend unit tests | **215 passed** (27 files) |
| Frontend production build | success (`vite build`) |
| Frontend eslint | success (`--max-warnings 0`) |
| Backend ruff (`app` + `tests`) | clean |
| Backend mypy | `mypy app/ai --follow-imports=silent` **Success**. `mypy app` still reports pre-existing **263** findings in 3 non-AI files (`pricing/snapshot_overlay.py`, `services/portfolio_service.py`, `persistence/result_payloads.py`) — same T15 policy. CI `lint-static-analysis` SUCCESS on HEAD `97cb4ed`. |
| GitHub CI on `97cb4ed` | All SUCCESS (push 35531122080, pull_request 35531125281): backend-pytest, quantlib hard gate, frontend-test-build, lint, e2e, postgres smoke, PR-FAST, PR-FULL. `MERGEABLE` / `CLEAN`. |
| Playwright `tests/risk-query.spec.ts` | **1 passed** (`QUANTLINEAGE_E2E_UVICORN="python3 -m uvicorn" PLAYWRIGHT_USE_CHROMIUM=1`) |
| `tests/test_openai_live.py` (normal CI) | **skipped** (opt-in). Body now requires tool → `function_call_output` → `proposed_answer`. Not executed here (no `RUN_LIVE_AI_TESTS=1`). |
| Full-suite log OpenAI hosts | none (suite finished in ~33s; CI workflow has no OpenAI env) |
| `docker compose -f docker-compose.yml config` | renders; AI env on backend/worker only; frontend none |
| `docker compose -f docker-compose.shared.yml config` | renders with dummy `POSTGRES_PASSWORD` / token; same AI placement; frontend only `VITE_API_BASE_URL=same-origin` build arg |
| `git diff --check` | clean |
| PR mergeability vs `cursor/openai-risk-assistant` | `MERGEABLE` / `CLEAN` (read-only `gh pr view`) |

## Limitations

- Conversational OpenAI defaults to one executed tool plus reserved narration (`AI_ASSISTANT_LOOP=conversational`, `AI_MAX_TOOL_ROUNDS=2`, `AI_MAX_TOOL_CALLS=1`). Explicit `AI_ASSISTANT_LOOP=router` is one-shot and never `model-narrated`.
- Conversation state is in-memory (24h TTL, 8 turns) and does not survive process restarts. Shared deployments must add persistence for durable chat.
- Live OpenAI smoke is opt-in only (`RUN_LIVE_AI_TESTS=1` + key + model). Normal CI makes no OpenAI network call. This C12 run did not execute the live smoke (no key/flag).
- Worker process does not independently construct a separate OpenAI client beyond shared env; interactive query path is lifespan-wired.
- Agent VM used Python 3.12.3; Docker images target 3.13.
- `frontend/.env.development` (`VITE_API_BASE_URL=same-origin`) remains from an earlier commit on this PR (`dd291ac`); it carries no OpenAI secret.

## Follow-ups

- Persist conversation state beyond in-memory (24h TTL, max 8 turns) for shared deployments.
- Run opt-in live smoke against the chosen production model before enabling OpenAI by default in shared deployments.
- Optional: wire worker-only AI path if workers ever need model routing (currently unused).
