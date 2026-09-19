# T13 Report — Wire Compose and operator guide

## Status
Complete.

## Changes
- `docker-compose.yml` — backend/worker receive AI env vars from project `.env`; frontend unchanged.
- `docker-compose.shared.yml` — same AI vars on backend/worker; comments point to platform secrets / `.env.shared`.
- `docs/openai_risk_assistant.md` — operator guide (default, enablement, fallback, cost, rollback).
- `docs/mcp.md` — explicit: MCP has no embedded LLM or `OPENAI_API_KEY`.
- `README.md` — one-line pointer to operator guide.
- `docs/ai/TASKS.md` — T13 marked complete.

## Checks
| Check | Result |
|---|---|
| YAML parse `docker-compose.yml` | OK |
| YAML parse `docker-compose.shared.yml` | OK |
| AI vars on backend/worker only | 6 vars each; frontend env/build args empty |
| `docker compose config` | Skipped — `docker` CLI not installed in agent VM |

## Concerns
- Run `docker compose config` and `docker compose -f docker-compose.shared.yml config` in an environment with Docker before merge to T15 gate.

## Branch
`feature/openai-risk-assistant`
