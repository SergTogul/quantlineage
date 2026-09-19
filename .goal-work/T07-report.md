# T07 — Provider factory and lifecycle wiring

## Status

Complete.

## Changes

- Added `backend/app/ai/factory.py` with `load_application_dotenv`, `RiskAssistantResources`, and `build_risk_assistant_resources`.
- Wired FastAPI lifespan in `backend/app/main.py`: load `.env` once (`override=False`), build AI resources once, store `ai_settings` / `risk_assistant_model` on `app.state`, pass model into `build_portfolio_service`, close SDK client on shutdown.
- Added optional `risk_assistant_model` constructor param to `PortfolioService` and `build_portfolio_service` (no `query` behavior change — T08).
- Added `backend/tests/test_ai_provider_factory.py`.

## Acceptance

| Criterion | Result |
|-----------|--------|
| Deterministic mode constructs no OpenAI client | Factory + lifespan tests mock `OpenAI` and assert zero calls |
| OpenAI mode constructs one reusable client/provider | Single `OpenAI()` + `OpenAIRiskAssistantModel` per lifespan |
| No mutable global test state | Resources live on `app.state`; tests use env monkeypatch + mocks |
| Dependency overrides remain possible | Test replaces `app.state.risk_assistant_model` after startup |
| Startup/shutdown covered | Lifespan sets state; `close()` called on TestClient exit |
| Config errors actionable, no key leak | `ValueError` messages name missing vars; sentinel key absent from text |

## Checks

```bash
cd backend
python3 -m pytest tests/test_ai_provider_factory.py tests/test_api.py -q
```

Result: 12 passed.

## Concerns

- Worker process (`app.worker`) does not yet load dotenv or AI resources; deferred to T13 Compose/operator wiring.
- `PortfolioService.query` still uses deterministic `answer()` until T08.
