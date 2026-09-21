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

## Test evidence (C12 merge gate, post C13–C19)

Independent coordinator rerun on `cursor/risk-query-incomplete-fallback-bebd`
at HEAD `2005f3c`, after C19 product `a8b1422` / evidence `f3fccf4`. Base
`cursor/openai-risk-assistant` is `0b6a4dc` (also the merge-base; no rebase
required). Python 3.12.3.

Documented C12 Checks passed. Opt-in live OpenAI smoke **skipped** (not
passed): this environment has no `OPENAI_API_KEY`. A skipped live test is
not passing evidence; it is an explicit remaining limitation, matching T14
and the original C12 close.

| Check | Result |
|---|---|
| Backend full suite | **2207 passed**, 10 skipped, 1 warning (**32.42s**, exit 0) |
| Frontend unit tests | **218 passed** (27 files) |
| Frontend production build | success (`vite build`) |
| Frontend eslint | success (`--max-warnings 0`) |
| Backend ruff (`app` + `tests`) | clean |
| Backend mypy | `mypy app` **263** errors in the same 3 non-AI files as T15 (`pricing/snapshot_overlay.py` 194, `services/portfolio_service.py` 68, `persistence/result_payloads.py` 1 error + 1 note). Zero findings in every C13–C19 AI/API/cache file (`policy`, `request_builder`, `assistant`, `config`, `narration`, `conversations`, `openai_model`, `api/risk`, `pricing/cache`). `mypy app/ai --follow-imports=silent` Success (11 files). CI `lint-static-analysis` uses `mypy app`. |
| Playwright `tests/risk-query.spec.ts` | **2 passed** (worst-stress + two-turn `conversation_id`) with `QUANTLINEAGE_E2E_UVICORN="python3 -m uvicorn" PLAYWRIGHT_USE_CHROMIUM=1` |
| `tests/test_openai_live.py` | **skipped**: requires `OPENAI_API_KEY` and `RUN_LIVE_AI_TESTS=1`. Still skipped with only the run flag. Not passing evidence. |
| Full-suite log OpenAI hosts | none (suite finished in 32.42s; CI workflow has no OpenAI env / `RUN_LIVE_AI_TESTS`) |
| `docker compose config` | renders; AI env on backend/worker only; frontend none |
| `docker compose -f docker-compose.shared.yml config` | renders with dummy `POSTGRES_PASSWORD` / token; same AI placement; frontend only `VITE_API_BASE_URL=same-origin` build arg |
| `git diff --check` | clean |
| PR mergeability vs `cursor/openai-risk-assistant` | `MERGEABLE` / `CLEAN` (read-only `gh pr view`). Targeting unchanged. GitHub CI on `2005f3c` **SUCCESS**. |

Post-review product SHAs on this branch: C13 `028a49d`, C14 `b8b371c`, C15 `fb9a3cf`, C16 `893c47a`, C17 `7d435ab`, C18 `8673895`, C19 `a8b1422`.

## Limitations

- Conversational OpenAI defaults to one executed tool plus reserved narration (`AI_ASSISTANT_LOOP=conversational`, `AI_MAX_TOOL_ROUNDS=2`, `AI_MAX_TOOL_CALLS=1`). Explicit `AI_ASSISTANT_LOOP=router` is one-shot and never `model-narrated`.
- Conversation state is in-memory (24h TTL, 8 turns, 2048-byte context, 8 conversations per principal) and does not survive process restarts. Shared deployments must add persistence for durable chat.
- Live OpenAI smoke is opt-in only (`RUN_LIVE_AI_TESTS=1` + key + model). Normal CI makes no OpenAI network call. This C12 rerun did **not** execute the live smoke (no key). The test file exists (`a5d3337`) and encodes tool selection → canned `function_call_output` → narration, but a skip is not a pass.
- Compose chat stays on interactive `POST /risk/query` (not a worker job). HEAVY RiskRuns remain on `/risk/runs`.
- Agent VM used Python 3.12.3; Docker images target 3.13.
- `frontend/.env.development` (`VITE_API_BASE_URL=same-origin`) remains from an earlier commit on this PR (`dd291ac`); it carries no OpenAI secret.
- Browser Retry-after-error was proven with vitest, not a live Compose UI session (no `/tmp/cursor/start-user` services). Playwright covered two-turn deterministic chat.

## Follow-ups

- Operator-run only: `cd backend && RUN_LIVE_AI_TESTS=1 python3 -m pytest tests/test_openai_live.py -q` with an authorized `OPENAI_API_KEY` and `OPENAI_MODEL`. Do not invent a key; do not treat a skip as a pass.
- Persist conversation state beyond in-memory (24h TTL, max 8 turns) for shared deployments.
- Optional: wire worker-only AI path if workers ever need model routing (currently unused).
