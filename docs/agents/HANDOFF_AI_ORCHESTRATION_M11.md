## Task
M11 AI risk assistant orchestration completion slice

## Owner
AI Orchestration Engineer

## Summary
Completed the remaining Workstream 11 AI assistant slice by adding a provider-agnostic one-turn model/tool orchestration contract on top of the existing deterministic router and QuantLineage tool executor. A model can now request exactly one supported deterministic tool, ask for clarification, or refuse unsupported/advisory prompts; QuantLineage executes the tool and formats final answers only from returned tool payloads.

## Files changed
- `backend/app/risk/query.py`
- `backend/tests/test_ai_query_orchestration.py`
- `docs/agents/HANDOFF_AI_ORCHESTRATION_M11.md`

## Public/interface changes
- Existing `/risk/query` and `/api/v1/risk/query` behavior is preserved and still uses the deterministic router by default.
- New provider-agnostic orchestration types in `app.risk.query`:
  - `RiskAssistantModelRequest`
  - `RiskAssistantModelResponse`
  - `RiskAssistantModel` protocol
  - `DeterministicRiskAssistantModel` offline adapter
- New `RiskQueryEngine.answer_with_model(...)` path:
  - sends serializable deterministic tool contracts to the model adapter;
  - accepts one selected `RiskToolName`, clarification, or refusal;
  - executes only known deterministic QuantLineage tools;
  - ignores any model-proposed answer text until after tool payloads are returned.
- Existing response metadata remains backward-compatible:
  - `tool_name: str | None`
  - `requires_clarification: bool`
  - `data.tool_contract`
  - `data.tool_result`
  - `data.supported_tools` for unsupported/clarification responses

## Numerical conventions
- Units: unchanged from the backing QuantLineage service payloads.
- Sign convention: unchanged from the backing deterministic service payloads.
- Day count/calendar if relevant: not changed.
- Tolerances/reference: no new numerical methodology. Tests use fixture values to prove answer text is sourced from deterministic tool results and not from model text.

## Tests added/updated
- `test_m11_tool_contracts_cover_core_questions`: verifies core deterministic tool schema coverage and backing service methods.
- `test_m11_router_selects_supported_tools_deterministically`: verifies supported prompts select the expected tool.
- `test_m11_numeric_answers_are_grounded_in_tool_payloads`: verifies numeric answer text comes from the selected fixture tool result.
- `test_m11_unsupported_question_refuses_without_running_risk_tool`: verifies unsupported advisory prompt refuses and does not call risk tools.
- `test_m11_ambiguous_risk_question_asks_for_clarification_without_numbers`: verifies ambiguous risk prompt asks for clarification without numbers.
- `test_m11_query_endpoint_exposes_tool_contract_metadata`: verifies `/api/v1/risk/query` exposes selected tool contract metadata.
- `test_m11_model_tool_loop_executes_selected_deterministic_tool`: verifies a model-selected tool is executed through QuantLineage only.
- `test_m11_model_answer_is_ignored_until_tool_payload_returns`: verifies model-proposed numerical text is not used in the final grounded answer.
- `test_m11_model_clarification_does_not_execute_numerical_tool`: verifies ambiguous model output returns clarification metadata without service calls.
- `test_m11_model_refusal_does_not_execute_risk_tool`: verifies advisory/unsupported model output refuses without service calls.

## Commands executed
```bash
cd backend
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=builtin .venv/bin/python -m pytest tests/test_ai_query_orchestration.py -q
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=builtin .venv/bin/python -m pytest tests/test_ai_query_orchestration.py -q
.venv/bin/python -m ruff check app/risk/query.py tests/test_ai_query_orchestration.py && .venv/bin/python -m mypy app
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=builtin .venv/bin/python -m pytest tests/test_ai_query_orchestration.py -q && .venv/bin/python -m ruff check app/risk/query.py tests/test_ai_query_orchestration.py && .venv/bin/python -m mypy app
PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=builtin .venv/bin/python -m pytest -q
```

## Results
- Backend:
  - Initial focused red run for this slice: `tests/test_ai_query_orchestration.py` failed at collection because `RiskAssistantModelRequest` did not exist.
  - Focused after implementation: `10 passed`, 1 known Starlette/httpx deprecation warning.
  - Full backend suite: `659 passed`, 1 known Starlette/httpx deprecation warning, in `133.62s`.
- Frontend: not run; UI not changed.
- QuantLib: not specifically run for this AI slice; no pricing/risk methodology changed.
- C++: not run; native code not changed.
- Build: not run; backend-only AI/query change.
- Static:
- First scoped Ruff run failed on an unused test import introduced during TDD; fixed before completion.
- Final scoped Ruff on touched files: `All checks passed!`.
- Mypy: `Success: no issues found in 82 source files`.
- All tests pass (all applicable/affected suites required by the task): yes for focused AI/query and full backend pytest.
- Unexplained failures or skips: none.
- CI is green (all required checks): not started by this subagent; no push performed.

## Known limitations / risks
- No live LLM provider adapter is configured in this repository; the abstraction is provider-agnostic and tests use an offline scripted/deterministic model, so no credentials or network are required.
- The deterministic router remains intentionally conservative keyword routing and is used as the offline adapter.
- Tool contracts currently cover core query tools requested for this slice; they do not yet include hedge compare, P&L explain, factor risk, or risk-run lookup from the broader AI charter.
- Query answers are concise strings grounded in tool payloads; richer citation-style narratives can be layered on top of the same `tool_result` payloads.

## Follow-up / next owner
- Owner: AI Orchestration Engineer
- Requested action: broaden tool contracts/evals to remaining broader-charter tools when product scope expands.
- Blocking?: no for this M11 completion slice. Parent/Lead should update `ROADMAP.md` and run/push CI as part of integration.
