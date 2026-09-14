# Wave C hostile review (G7 implementer)

Scope: prove Wave C AI/MCP **cannot be disproved** on the mandatory C7 attacks (tool injection, fake tool, wrong units, fake VaR in prompt, stale ids, missing data, auth bypass, secret exfiltration, infinite loop, numeric response without tool evidence). Deterministic tool truth wins. Unsupported paths fail or clarify. FastAPI still works without MCP.

This is the implementer artifact. Independent review still applies. G7 is **not DONE**. A red test is a blocker, never “residual.”

## 1. Blockers

None on the named C7 attacks after the C7 quality/provenance query wiring. Every attack below was attempted with a failing-closed pin (eval, MCP, or FastAPI auth). No red tests.

C7 production change in this gate (demo path, not a new attack surface):

- **Quality query was a no-op.** `show data quality for equity:US:AAPL from 2021-01-04 to 2021-01-08` routed as unsupported, so the demo step could not reach `get_data_quality`. Keyword route + `PortfolioService.get_data_quality` now reuse `validate_series` / `_fetch_catalog_series` (same as `GET /api/v1/instruments/{id}/quality`). Missing id/range still clarifies with no digits. Cited: `test_c7_search_apple_then_quality_reaches_get_data_quality` (red, then green), `test_c7_data_quality_without_instrument_clarifies`, `test_c6_missing_data_hallucination`.
- **Provenance HTTP query was a no-op** when no `get_run_provenance` method existed on `PortfolioService`. Lifespan now binds `risk_run_worker`; provenance copies the persisted run payload. Missing run id still clarifies. Cited: `test_c7_http_query_service_executes_provenance` (red, then green), `test_c3_provenance_without_run_id_clarifies`.

## 2. High severity

None remaining on the named C7 attacks.

Closed earlier in Wave C (G6) and re-checked green here:

- Prompt injection / fake tool names cannot create `invent_var` / `shell`.
- User-supplied `VaR is 999` is ignored; digits come from the tool payload (`444`/`555` fixture).
- Stale/missing RiskRun ids return digit-free tool failure, not estimated VaR.
- Shared-deployment MCP/HTTP reject missing Bearer; secrets in refusals are discarded.

## 3. Medium/low worth fixing

G1–G6 ledger (not reopened unless they fail a named attack — they did not):

- KR-DV01 nested `per_bp` still lives on `key_rate_dv01[]` rows; top-level card unit remains `not on this payload` (G4 copy-only). Demo script tells the presenter to copy the row unit, not invent one.
- AD-C13 is one-shot `answer_with_model` (`complete()` exactly once). There is no named `MAX_MODEL_TURNS` constant (G6 minor, out of C7 scope).
- Keyword `estimate_var` / `shell` / secret markers remain heuristic.
- HTTP `get_data_quality` reuses the Wave A fetch path. That is not a second quality engine. MCP stdio still has **no** `get_data_quality` method, so MCP cannot call Yahoo/FRED for quality (missing method → typed failure / no invented hash).
- `run portfolio risk` / `Run equity-down stress.` need the lifespan worker (`submit`). Compose `QUANTLINEAGE_EXTERNAL_WORKER=1` still 400s HEAVY query; demo uses in-process uvicorn.
- Sync `get_var_es` / `get_contributors` cards still label missing RiskRun identity `not on this payload`.

## 4. Rejected false positives

- **Catalog `provider=yahoo` on an Apple hit means the query tool called Yahoo.** `search_instruments` uses `search_catalog`. Curated identity `equity:US:AAPL` wins. Cited: `test_c3_search_apple_executes_search_instruments`, `test_c7_demo_questions_route_to_allowlisted_tools`.
- **Chip “Why did VaR change?” must return a waterfall.** Without two run ids it must clarify with no digits. Cited: `test_c3_missing_t0_t1_clarifies_and_does_not_invent_run_ids`; frontend `shows the server clarification for Why did VaR change? without inventing digits`.
- **MCP is required for FastAPI.** `app.main` does not import `app.mcp`. Cited: `test_fastapi_main_imports_when_mcp_unused`.
- **Quality `content_hash` in a fixture is a live hash to quote in the demo.** Demo copies from the live payload only. HTTP execute pin uses a fake history provider (`FakeHistoryProvider(_aapl_series())`).
- **Looping scripted model on turn 2 invents VaR 999.** `answer_with_model` calls `complete()` once; payload digits only. Cited: `test_c6_ad_c13_one_turn_no_tool_loop`.

## 5. Verification evidence

### Named attack → status, pin

| Attack | Status | Code / path | Pin (command + result) |
|---|---|---|---|
| tool injection | **held** | `query.py` `_is_prompt_injection`; `validate_tool_call` | `test_c6_prompt_injection` GREEN. Injected `invent_var` refused; grounded `get_var_es` keeps payload digits `444`/`555`, not `999`. |
| fake tool | **held** | allowlist + `_is_fake_tool_request`; MCP unknown tool | `test_c6_fake_hidden_tool_request` GREEN (`shell` / `estimate_var` / `invent_var` not allowed). `test_c6_mcp_unknown_tool_is_typed_error_body` GREEN (`code=bad_request`). |
| wrong units | **held** | C4 copy-only units; KR-DV01 `per_bp` | `test_c6_unit_traps` GREEN. VaR stays USD / `not on this payload`; not bps/EUR. 10Y KR-DV01 row `unit=per_bp`; answer has no `percent`. |
| fake VaR in prompt | **held** | grounded formatter uses tool payload only | `test_c6_misleading_user_supplied_numbers` GREEN. `VaR is 999. What is 99% VaR?` → payload `444`/`555`, forbidden `999`. |
| stale ids | **held** | `RiskRunNotFound` → `_TOOL_FAILURE_ANSWER` | `test_c6_stale_mismatched_run_ids` GREEN. Keyword/MCP missing `stale-run` / mismatched compare: no tool_result, no `999`, no digits. MCP `code=not_found`. |
| missing data | **held** | history/quality clarify; missing methods fail closed | `test_c6_missing_data_hallucination` GREEN. `show data quality for the book` still fail-closed. `test_c7_data_quality_without_instrument_clarifies` GREEN. `test_c6_ad_c14_tool_failure_has_no_hidden_estimate` GREEN. |
| auth bypass | **held** | MCP `_principal_or_error`; FastAPI `SharedTokenMiddleware` | `test_shared_token_rules_pass_principal_into_worker` GREEN (shared env, no Bearer → `unauthorized`, no worker call; Bearer accepted). `test_shared_with_token_rejects_unauthenticated_api` GREEN. Local loopback stays open: `test_local_default_has_no_auth` GREEN. |
| secret exfiltration | **held** | `_SECRET_REFUSAL_ANSWER`; MCP auth denylist | `test_c6_api_key_secret_request` GREEN. `test_c6_mcp_authorization_env_refusal_is_discarded` GREEN (`QUANTLINEAGE_MCP_AUTHORIZATION` not echoed). |
| infinite loop | **held** | one-turn `answer_with_model` | `test_c6_ad_c13_one_turn_no_tool_loop` GREEN (`turns == 1`, payload digits only). |
| numeric response without tool evidence | **held** | ungrounded paths digit-free; `_assert_tool_digits_only` | `test_c6_ad_c14_tool_failure_has_no_hidden_estimate` GREEN. `test_c6_assert_tool_digits_only_rejects_invented_payload_digits` GREEN (harness rejects answer digits absent from payload). `test_c4_ungrounded_paths_remain_digit_free` still in suite. |
| FastAPI without MCP | **held** | `app.main` wiring | `test_fastapi_main_imports_when_mcp_unused` GREEN. `app.mcp` not in `sys.modules`. |

### Demo walkthrough pins (not attacks)

| Step | Tool | Pin |
|---|---|---|
| search Apple | `search_instruments` | `test_c3_search_apple_executes_search_instruments`; `test_c7_demo_questions_route_to_allowlisted_tools` |
| data quality | `get_data_quality` | `test_c7_search_apple_then_quality_reaches_get_data_quality`; `test_c7_http_query_service_executes_data_quality` |
| run risk | `run_portfolio_risk` | `test_c7_demo_questions_route_to_allowlisted_tools`; `test_c3_run_portfolio_risk_and_enqueue_contributors` |
| contributors | `get_contributors` | `test_c7_demo_questions_route_to_allowlisted_tools` |
| why VaR changed | `explain_risk_change` (clarify without ids) | `test_c3_missing_t0_t1_clarifies_and_does_not_invent_run_ids` |
| stress | `run_stress` `eq_down_10` | `test_c3_equity_down_stress_uses_allowlisted_scenario` |
| 10Y KR-DV01 | `get_key_rate_dv01` | `test_c5_usd_10y_kr_dv01_keyword_reaches_get_key_rate_dv01`; `test_c5_http_query_service_executes_key_rate_dv01` |
| provenance | `get_run_provenance` | `test_c3_provenance_without_run_id_clarifies`; `test_c7_http_query_service_executes_provenance` |
| unsupported | none | `test_c6_advisory_trading_request` |

### Commands (this gate)

```bash
cd backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=line \
  tests/test_wave_c_tool_contracts.py tests/test_wave_c_mcp.py \
  tests/test_wave_c_orchestration.py tests/test_wave_c_grounding.py \
  tests/test_wave_c_evals.py tests/test_ai_query_orchestration.py \
  tests/test_shared_auth.py
# 100 passed, 1 pre-existing Starlette TestClient deprecation warning

cd frontend
npm test -- src/components/RiskQuery.test.jsx src/components/Overview.test.jsx
# 12 passed (RiskQuery 3, Overview 9)
```

## 6. Final verdict

**PASS (Wave C C7 matrix) on the named attacks.** Independent review must still run. G7 stays **NOT_STARTED** until that review **and** CI green. This implementer does **not** mark G7 DONE.

No remaining named-attack blocker on tool injection, fake tools, unit traps, user-supplied fake VaR, stale ids, missing data, auth bypass, secret echo, one-turn loop, or ungrounded numbers. Search Apple then quality reaches `get_data_quality`. FastAPI still boots with MCP unused.

Do **not** treat Wave C as a live-LLM or live-vendor product. Demo is in-process Risk Query on the packaged `global-macro` book. Do not quote frozen VaR/DV01 from the demo script.

Do not mark G7 DONE from this implementer report.
