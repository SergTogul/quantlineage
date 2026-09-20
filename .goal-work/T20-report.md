# T20 Report — Multi-tool RiskAssistant protocol

## Status

**DONE** (T21–T24 remain OPEN)

## Summary

Added a higher-level `RiskAssistant` protocol that proposes turns and never executes tools. Milestone 1 `RiskAssistantModel.complete` remains the live query path. `OneToolRiskAssistant` wraps that adapter for T21.

## Files

| File | Purpose |
|------|---------|
| `backend/app/ai/assistant.py` | Protocol, request/turn types, one-tool adapter |
| `backend/app/ai/factory.py` | Expose `assistant` wrapper beside `model` |
| `backend/app/main.py` | Store `app.state.risk_assistant` without changing query execution |
| `backend/tests/test_ai_assistant_protocol.py` | Adapter and factory contract tests |
| `docs/ai/GOAL.md` | Milestone 2 DoD; deferred ≠ done |
| `.cursor/DEFERRED_NOT_DONE.md` | Guardrail that T20–T24 are still open |

## Design

1. `complete_turn` returns zero or more tool calls; the application executes them later (T21).
2. `OneToolRiskAssistant` maps one `RiskAssistantModelResponse` to at most one call (`call_0`).
3. Follow-up rounds (`round_index != 0` or `prior_outputs`) fail closed without calling the inner model.
4. Factory/lifespan keep `risk_assistant_model` as `OpenAIRiskAssistantModel`.

## Checks

```bash
cd backend
python3 -m pytest tests/test_ai_assistant_protocol.py tests/test_ai_query_orchestration.py tests/test_openai_model.py tests/test_ai_provider_factory.py -q
# 62 passed
python3 -m pytest tests/test_ai_assistant_protocol.py tests/test_ai_query_orchestration.py tests/test_openai_model.py tests/test_ai_provider_factory.py tests/test_ai_security.py -q
# 79 passed
ruff check app/ai/assistant.py app/ai/factory.py app/ai/__init__.py app/main.py tests/test_ai_assistant_protocol.py tests/test_ai_provider_factory.py tests/test_ai_security.py
# All checks passed
```

## Out of scope (T21+)

- Responses `function_call_output` loop
- Raising `AI_MAX_TOOL_ROUNDS` above 1
- Numeric narration grounding
- Switching `PortfolioService.query` off `answer_with_model`
