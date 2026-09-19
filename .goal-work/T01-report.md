# T01 Report — Add typed AI configuration

## Status

**DONE**

## Summary

Implemented typed AI configuration at `backend/app/ai/config.py` with a minimal `backend/app/ai/__init__.py` re-export surface. Settings follow the frozen-dataclass + env-read pattern from `backend/app/persistence/config.py`.

## Files added

| File | Purpose |
|------|---------|
| `backend/app/ai/__init__.py` | Minimal exports; no client creation on import |
| `backend/app/ai/config.py` | `AISettings`, `get_ai_settings()`, `get_openai_api_key()` |
| `backend/tests/test_ai_config.py` | 14 unit tests covering all acceptance criteria |

## Design decisions

1. **`get_openai_api_key()`** — API key is read separately and never stored on `AISettings`, keeping repr/logs safe.
2. **Timeout cap** — `MAX_AI_TIMEOUT_SECONDS = 120` (brief suggested a sensible cap; plan says positive and capped).
3. **`max_tool_rounds`** — Defaults to `1` when unset; any other value raises (milestone 1 constraint).
4. **No dotenv / OpenAI SDK** — Deferred to T02 per scope; config reads `os.environ` only and never writes.
5. **Explicit kwargs on `get_ai_settings()`** — Mirrors `get_database_settings()` for testability.

## Acceptance mapping

| Criterion | Implementation |
|-----------|----------------|
| Provider defaults to `deterministic` | `_parse_provider` returns default when unset/blank |
| Supported providers exactly `deterministic` and `openai` | `_SUPPORTED_PROVIDERS` frozenset + validation |
| OpenAI mode requires key and model | Validated in `get_ai_settings` when provider is `openai` |
| Timeout and tool-round values bounded | Timeout `(0, 120]`; rounds must equal `1` |
| Key excluded from repr and error messages | Key not on dataclass; tests assert secret absent |
| Loading does not override exported env vars | Read-only `os.environ.get`; test compares env before/after |
| Import does not create client or network call | No OpenAI import; socket guard test on re-import |

## Checks

```bash
cd backend
python3 -m pytest tests/test_ai_config.py -q
# 14 passed in 0.39s
```

## Commits

| SHA | Subject |
|-----|---------|
| `833ed05` | Add typed AI configuration (T01) |
| (docs) | Mark T01 complete in TASKS.md |

## Out of scope (T02+)

- `python-dotenv` / `.env` loading
- OpenAI Python SDK dependency
- Provider factory or lifespan wiring

## Concerns

None.
