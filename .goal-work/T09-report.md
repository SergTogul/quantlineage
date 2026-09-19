# T09 — Optional assistant metadata

## Status

Complete.

## Summary

Added optional `data.assistant` metadata to risk-query responses when an AI provider is configured:

- `provider`: `deterministic` | `openai`
- `model`: configured model label (safe string; never the API key)
- `mode`: `model-routed` | `deterministic` | `fallback`
- `fallback`: boolean

Pure deterministic queries omit `assistant` for backward compatibility. Model-routed paths attach metadata on success, clarification, refusal, configuration errors, and transient fallback.

Removed prior `data.model` dumps that leaked rationale/tool args. Typed `RiskQueryAssistantMetadata` validates the wire shape; `POST /risk/query` now declares `response_model=RiskQueryResponse`.

## Files

- `backend/app/api/schemas/transport.py` — `RiskQueryAssistantMetadata`, response validator
- `backend/app/risk/query.py` — metadata builder and `answer_with_model` wiring
- `backend/app/services/portfolio_service.py` — pass `AISettings` context
- `backend/app/services/risk_factories.py`, `backend/app/main.py` — lifecycle wiring
- `backend/app/api/risk.py` — typed response model
- `backend/tests/test_ai_provider_integration.py` — metadata coverage

## Checks

```bash
cd backend
python3 -m pytest tests/test_api_typed_models.py tests/test_api_openapi_examples.py tests/test_ai_provider_integration.py -q
```

65 passed.

## Concerns

None. Deterministic default path unchanged; metadata appears only when a model adapter is configured.
