# T06 — Handle model and provider failures

## Status

Complete.

## Changes

- Added `backend/app/ai/errors.py` with typed provider/parse errors and secret redaction helpers.
- Extended `backend/app/ai/openai_model.py` to map SDK failures, reject incomplete outputs, sanitize numeric prose in zero-call clarifications, and log redacted request metadata.
- Expanded `backend/tests/test_openai_model.py` for parse edge cases, SDK error taxonomy, and redaction.

## Acceptance mapping

| Requirement | Implementation |
|---|---|
| Zero calls → clarification/refusal | Existing text/refusal paths; numeric prose replaced with safe default clarification |
| Multiple calls rejected | `OpenAIMultipleToolCallsError` |
| Unknown tools as candidates only | Adapter returns `tool_name` without execution |
| Malformed JSON / incomplete outputs | `OpenAIMalformedToolArgumentsError`, `OpenAIIncompleteResponseError` |
| Distinguishable provider failures | `OpenAITimeoutError`, `OpenAIRateLimitError`, `OpenAIServerError`, `OpenAIAuthenticationError`, `OpenAIConfigurationError` |
| No secrets in errors/logs | `sanitize_provider_message`, `redact_request_kwargs`, caplog regression test |

## Tests

```bash
cd backend
python3 -m pytest tests/test_openai_model.py -q
python3 -m pytest tests/test_ai_query_orchestration.py -q
```

Results: 23 passed (model), 20 passed (orchestration).

## Concerns

- `BadRequestError` and `NotFoundError` are classified as configuration failures; orchestration fallback wiring lands in T07/T08.
- Log `extra["request"]` retains non-secret routing fields for debugging; keys and auth material are redacted.
