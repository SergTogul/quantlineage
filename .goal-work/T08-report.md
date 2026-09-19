# T08 — Wire provider into PortfolioService.query

## Status

Complete.

## Changes

- `PortfolioService.query` routes to `answer_with_model` when `risk_assistant_model` is set; otherwise unchanged `answer()` path.
- `RiskQueryEngine.answer_with_model` catches transient OpenAI errors before tool execution and falls back to deterministic `answer()` with stub `data.assistant.fallback=true`; configuration/auth errors return actionable clarification without fallback (lazy import avoids circular dependency with `app.ai`).
- Added `backend/tests/test_ai_provider_integration.py` (7 cases).

## Checks

```bash
cd backend
python3 -m pytest tests/test_ai_query_orchestration.py tests/test_ai_provider_integration.py -q
```

Result: 27 passed.

## Concerns

- Full assistant metadata (provider, model label, mode) deferred to T09; only `fallback`/`error` stub present.
- Side-effect replay protection relies on fallback occurring only before `model.complete()` returns (no tool execution yet).
