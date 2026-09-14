# Wave C — C0 Integration Map

Inspected on `feat/quantlineage-wave-c` parent `ae5e092` (Wave B G7 DONE). This is the reuse map for C1 tool contracts. **Do not invent a parallel risk engine, MCP server (C2), or UI (C5).**

Core rule (ADR 006 / `AGENTS.md`): the model orchestrates; QuantLineage calculates. There is **no MCP server** yet. `RiskQueryEngine` is a keyword router plus optional `RiskAssistantModel` tool-selection turn; no live LLM.

Canonical HTTP prefix is `/api/v1`. Legacy dual-mount without the prefix still exists (`app.main` includes each domain router twice). C1/C2 should advertise `/api/v1` only.

## Current abstractions to reuse

| Concern | Reuse | Notes |
|---|---|---|
| RF-019 allowlist | `RiskToolName`, `TOOL_CONTRACTS`, `validate_tool_call`, `tool_json_schemas` (`backend/app/risk/query.py`) | Six tools today. Extra keys forbidden. Unknown names refused. Portfolio is bound by QuantLineage, never the LLM (`RiskToolArgs` is empty). |
| Keyword + optional model | `RiskQueryEngine.route` / `answer` / `answer_with_model`; `DeterministicRiskAssistantModel` | Keyword path calls `_execute_tool` with `{}` except `explain_risk_change` (always clarification until ids are supplied). `answer_with_model` still executes **service methods**, not model arithmetic. |
| NL HTTP | `POST /api/v1/risk/query` → `PortfolioService.query` | Body `RiskQueryRequest {portfolio, question}` → `RiskQueryResponse`. HEAVY. |
| Instrument search | `search_catalog` (`app.market.catalog.service`) | Curated Wave A universe wins identity; Yahoo search is injected hits only. |
| History | `GET /api/v1/market/history/{instrument_id}` | Normalized **levels** + `SeriesLineage`. Does **not** compute returns. Not Wave B wealth analytics. |
| Quality | `validate_series` → `GET /api/v1/instruments/{id}/quality` | Fail-closed; no interpolation. |
| Portfolio risk | `PortfolioService.summary` / `var_report`; `HistoricalRiskEngine.calculate` | Identity-preserving path is **RiskRun**, not the sync dump. |
| RiskRun lifecycle | `RiskRunWorker.submit` / `get`; `POST/GET /api/v1/risk/runs` | Typed `run_type` + `request` (`RISK_RUN_REQUEST_SCHEMAS`). Status QUEUED/RUNNING/COMPLETED/FAILED. |
| Flagship compare | `POST /api/v1/risk/runs/compare` → `RiskRunWorker.compare_runs` → `explain_risk_runs` (`risk_run_compare.py`) | Same engine as RF-019 `explain_risk_change`. Residual always present. |
| Stress | `PortfolioService.stresses` / `threat_evaluation`; `StressEngine` | Baseline includes `eq_down_10` (“Equities -10%”). |
| KR-DV01 | `GET /api/v1/market/rates-showcase` → `build_rates_showcase` → `SensitivityEngine` | Demo USD 2Y/5Y/10Y on the rates-macro book. Not a generic portfolio+tenor HTTP API. |
| Contributors | `PortfolioService.contributors` | Parametric component VaR; RF-019 truncates to 5. |
| Hedge compare (optional) | `PortfolioService.compare_scenarios` → `ScenarioComparisonEngine` | `POST /risk/stress/compare` and `/stress/formal/compare`; `run_type=stress_compare`. |
| Provenance (optional) | `GET /api/v1/risk/runs/{id}/provenance` → `RiskRunProvenance` | Copied from persisted run; no secrets; `release_sha` omitted when unknown. |
| Historical analytics (Wave B) | `POST /api/v1/risk/historical-analytics` | **Portfolio** wealth/drawdown/Sharpe/VaR-ES on a frozen panel. **Not** `get_market_history`. |
| Errors | `app.api.errors.ErrorBody` `{code, message, details}` | Plus RF-019 `ToolCallValidation.refusal` strings (not HTTP). |
| Auth | `SharedTokenMiddleware`; RF-014 `request_principal` on RiskRuns | `PortfolioAccessDenied` → 403 `forbidden`. |

## Dependency direction (must stay)

```text
MCP / RiskQueryEngine / LLM adapter
        → allowlisted tool schemas
        → existing application services / HTTP
                → HistoricalRiskEngine / StressEngine / SensitivityEngine / catalog
Browser / MCP MUST NOT call Yahoo/FRED, SQL, shell, or filesystem.
app.risk.* MUST NOT grow a second VaR/stress engine for AI.
```

## RF-019 tools today (must not rebuild)

| `RiskToolName` | Service method | Sync HTTP (also dual-mounted) | Result | C1 fate |
|---|---|---|---|---|
| `get_portfolio_summary` | `PortfolioService.summary` | `POST /risk/summary` | `RiskSummary` | Fold into `run_portfolio_risk` / `get_risk_run` (`run_type=summary`) |
| `get_var_es` | `PortfolioService.var_report` | `POST /risk/var` | `VaRReport` | Fold into `run_portfolio_risk` / `get_risk_run` (`run_type=var`) |
| `get_worst_stress` | `PortfolioService.threat_evaluation` | `POST /risk/stress/evaluate` | `ScenarioEvaluationReport` | Related to `run_stress`; keep as evaluate/worst view, not a new engine |
| `get_limits` | `PortfolioService.limits` | `POST /risk/limits` | `list[LimitResult]` | **Not** in C1 minimum list; leave allowlisted for RF-019 until C1 decides |
| `get_contributors` | `PortfolioService.contributors` | `POST /risk/contributors` | `list[Contributor]` | Maps to `get_top_risk_contributors` |
| `explain_risk_change` | `PortfolioService.explain_risk_change` → `risk_run_compare` | `POST /risk/runs/compare` | `RiskChangeReport` | Maps to C1 `explain_risk_change` (and shares engine with `compare_risk_runs`) |

`ExplainRiskChangeArgs`: `t0_run_id`, `t1_run_id` (min_length 1), `metric: str = "var_99"` — **extend schema** in C1 to the `RiskChangeMetric` literal used by `RiskRunCompareRequest`. Keyword `route()` never executes this tool without ids (always clarification).

## C1 proposed tools → existing services

Status: **reuse** = call as-is; **extend schema** = same engine, tighter/wider tool JSON Schema or identity fields; **missing** = no application service today (do not invent math; C1 must not claim it).

### search_instruments — **reuse** (extend schema for C1 args)

| | |
|---|---|
| Service | `search_catalog(q, provider=…)` |
| HTTP | `GET /api/v1/instruments/search?q=` |
| Args | `q: str`. Empty/whitespace → `[]` (not an error). |
| Result | `list[CatalogSearchHit]`: `instrument_id`, `display_name`, `provider`, `source_symbol`, `asset_type`, `currency`, capability flags, optional `risk_factor_mapping`, `coverage`. Curated ids (e.g. `equity:US:AAPL` / “Apple Inc.”) win over Yahoo. |
| Identities | Catalog `instrument_id` only. No RiskRun. |
| Unit / sign | None (metadata). |
| Errors | Provider-only failure with no hits → mapped `ProviderError` (`unavailable` 503, `rate_limited` 429, `authorization` 401, `not_found` 404, `malformed_response` / `insufficient_history` 502). |
| C1 note | Add `q` min_length; do not expose a general HTTP tool. Tests: `test_catalog_search.py`, product API tests. |

### get_market_history — **reuse**

| | |
|---|---|
| Service | `_fetch_catalog_series` + `validate_series` |
| HTTP | `GET /api/v1/market/history/{instrument_id}?start&end` |
| Args | Path `instrument_id`; query `start`, `end` ISO dates (**required** — `None` is 400 `bad_request`). Max span `MAX_HISTORY_RANGE_DAYS = 1826`. Inverted range 400. |
| Result | `InstrumentHistoryOut` = `SeriesLineage` + `points[{observation_date, value}]`. Levels only. |
| Identities | `instrument_id`, `source`, `source_symbol`, `content_hash`, `normalization_version`, `first_observation` / `last_observation`. |
| Unit / sign | `unit` ∈ `{price, percent}` as stored; **no** return conversion, **no** FRED percent→decimal here. |
| Errors | 404 `not_found` (unknown instrument or empty series); 400 series codes (`unsorted_dates`, `duplicate_dates`, `non_finite_value`, `non_positive_price`, `unknown_unit`, `insufficient_observations`); provider taxonomy as above. |
| C1 note | Do **not** map this to `POST /risk/historical-analytics`. That is portfolio wealth on a frozen factor panel. |

### get_data_quality — **reuse**

| | |
|---|---|
| Service | same fetch path + `validate_series` (no points in the response) |
| HTTP | `GET /api/v1/instruments/{instrument_id}/quality?start&end` |
| Args | Same date parse as history, **without** the 1826-day cap. |
| Result | `SeriesLineage`: counts, `stale` (7-day vs requested end), `content_hash`, `missing_count`, `duplicate_count`. |
| Identities | Same series identity as history. |
| Unit / sign | Declared `unit` / `currency` / `frequency` / `adjustment` only. |
| Errors | Same 404 / 400 / provider mapping. |
| Evidence | `test_quality_lineage.py`, `test_instrument_quality_api.py`. |

### run_portfolio_risk — **reuse** engine; **extend schema** for tool identity

| | |
|---|---|
| Service | `HistoricalRiskEngine.calculate` via `PortfolioService.summary` / `var_report`; enqueue via `RiskRunWorker.submit` |
| HTTP (preferred) | `POST /api/v1/risk/runs` `{portfolio, run_type, request, market_snapshot_id}` → 202 `RiskRunView`; poll `GET /api/v1/risk/runs/{id}` |
| HTTP (sync, no run id) | `POST /api/v1/risk/summary`, `POST /api/v1/risk/var` (HEAVY; FULL_REVALUATION summary refuses inline) |
| `run_type` | `summary` / `var` / `dashboard` (also `es`, `var_compare`). Request: `methodology`, optional dataset id/version, `as_of`, `calculation_config`. Extra keys forbidden. |
| Result | Typed RiskRun result payload (`RiskSummary` / `VaRReport` / dashboard batch). |
| Identities | `risk_run_id`, `portfolio_id`, `portfolio_version`, `market_snapshot_id`, `historical_dataset_id` / `version`, `as_of`, `methodology`. |
| Unit / sign | VaR/ES: **currency loss**, `max(0, quantile)` on losses (`-pnl`). MV: currency. Greeks: engine units (`dv01` per_bp on sensitivities path). |
| Errors | 400 `bad_request` (unknown `run_type`, validation); 403 ACL; 422 `validation_error`; run `FAILED` + `error_message`. |
| C1 note | RF-019 `get_portfolio_summary` / `get_var_es` dump sync payloads **without** run identity. C4 requires run/dataset/snapshot on numeric answers — C1 schema should wrap **RiskRun**, not replace the engine. |

### get_risk_run — **reuse**

| | |
|---|---|
| Service | `RiskRunWorker.get` / `RiskRunService.get` |
| HTTP | `GET /api/v1/risk/runs/{run_id}` |
| Args | `run_id: str` |
| Result | `RiskRunView`: status, spec, `results[]` with typed payloads, timestamps, `error_message`. |
| Identities | Full run header (snapshot, dataset, methodology, `as_of`). |
| Unit / sign | Pass through stored payloads; do not recompute. |
| Errors | 404 `risk run not found: {id}` (string detail today — C1/C2 should keep `ErrorBody` via handler); 403 `forbidden`. |
| C1 note | Read-only / idempotent. Stale ids fail closed — never estimate. |

### compare_risk_runs — **reuse** (same engine as explain)

| | |
|---|---|
| Service | `RiskRunWorker.compare_runs` → `explain_risk_runs` |
| HTTP | `POST /api/v1/risk/runs/compare` |
| Args | `RiskRunCompareRequest`: `t0_run_id`, `t1_run_id`, `metric` ∈ `{var_99, var_95, expected_shortfall_99, dv01, vega, stress}` default `var_99`. Extra forbid. HEAVY. |
| Result | `RiskChangeReport` (full waterfall + residual + identity diff). |
| Identities | `t0_run_id`, `t1_run_id`, `identity` (`RiskRunIdentityDiff`), disclosed config/dataset/snapshot changes. Both runs must be **COMPLETED**. |
| Unit / sign | `unit` / `sign_convention` on the report. VaR/ES: currency loss; positive `total_change` = more loss-risk. DV01: currency per 1bp. Vega: engine vega. Stress: scenario **P&L** (not loss); positive `total_change` = P&L increased. Reconciliation: `portfolio_trade_change + market_change + residual == total_change` (abs 1e-6 / rel 1e-8). |
| Errors | 404 missing run; 403 ACL; 400 if not both COMPLETED or metric/bind failure (`Invalid request`). |
| C1 note | Do not add a second compare kernel. If C1 keeps both this tool and `explain_risk_change`, they **must** share `compare_runs`. Optional **extend schema**: a thinner compare view that still returns the same `RiskChangeReport` fields (or an explicit subset) without new math. |

### explain_risk_change — **reuse**

| | |
|---|---|
| Service | Same as `compare_risk_runs`; RF-019 `RiskToolName.EXPLAIN_RISK_CHANGE` → `PortfolioService.explain_risk_change` (requires `service.risk_run_compare` wired, as the API worker does). |
| HTTP | Same `POST /api/v1/risk/runs/compare`. Keep `POST /risk/change-attribution` for **portfolio-pair** waterfall — not the C1 two-run tool. |
| Args | Align RF-019 `ExplainRiskChangeArgs.metric: str` with `RiskChangeMetric`. |
| Result / units / errors | Identical to `compare_risk_runs`. |
| C1 note | Keyword engine currently **clarifies** (“Provide two completed RiskRun identifiers… Do not invent VaR.”) and does not guess ids. Preserve that. |

### run_stress — **reuse** engine; **extend schema** for allowlisted scenarios

| | |
|---|---|
| Service | `PortfolioService.stresses` → `StressEngine.run`; threat view `threat_evaluation` |
| HTTP | `POST /api/v1/risk/stress` (baseline `DEFAULT_SCENARIOS`, includes `eq_down_10` / “Equities -10%”); custom `POST /risk/stress/formal/custom`; evaluate `POST /risk/stress/evaluate`. Async: `run_type=stress` or `stress_evaluate`. |
| Args | Portfolio + optional formal `ScenarioWire` list. C1 should allowlist named scenarios (C7: “equity-down”) rather than arbitrary shocks. |
| Result | `list[StressResult] {scenario, pnl, by_position}` or `ScenarioEvaluationReport` (`worst_scenario`, `worst_loss`, evaluations). |
| Identities | Prefer RiskRun (`run_type=stress*`) so C4 can stamp snapshot/dataset. Sync stress has portfolio + implied snapshot only. |
| Unit / sign | `pnl` currency; **negative = loss**. Evaluate `loss = max(0, -pnl)`; `loss_pct_nav` vs `|base MV|`. |
| Errors | HEAVY refuse → use `/risk/runs`; 400 validation; 403 ACL. |
| C1 note | RF-019 `get_worst_stress` is **evaluate**, not a generic custom shock. Reverse-stress routes exist but are out of C1 minimum. |

### get_key_rate_dv01 — **reuse** demo path; **missing** generic book API

| | |
|---|---|
| Service | `build_rates_showcase` → `SensitivityEngine.calculate(..., measures=("dv01","key_rate_dv01"))` |
| HTTP | `GET /api/v1/market/rates-showcase` (no args). Demo `RATES_MACRO_PORTFOLIO` + `demo_market_snapshot`. |
| Result | `RatesShowcaseView`: `portfolio_id`, `market_snapshot_id`, `conventions`, curve nodes, `parallel_dv01`, `key_rate_dv01[{tenor, factor, value, unit, method}]` for USD **2Y / 5Y / 10Y**. |
| Identities | Showcase `portfolio_id` + `market_snapshot_id`. Not a caller RiskRun. |
| Unit / sign | Shock: 1bp = `1e-4` decimal. Sensitivity: **currency P&L per +1bp** (`unit=per_bp`). Long rates typically **negative**. KR_2Y ≠ KR_10Y; sum of 2Y/5Y/10Y ≠ parallel when extra pillars apply. Documented in `RATES_SHOWCASE_CONVENTIONS`. |
| Errors | 500-class if snapshot lacks `USD_OIS` (builder `ValueError`). |
| C1 note | C7 “Show USD 10Y KR-DV01” can **filter the showcase payload** in the tool layer (extend schema: optional `tenor=10Y`). There is **no** `POST /risk/sensitivities` for an arbitrary book. Do not add a second bump engine; if C1 needs a non-demo book, wrap `SensitivityEngine` already used by the showcase (still not new math) — call that **extend schema**, not missing math. |

### get_top_risk_contributors — **reuse**

| | |
|---|---|
| Service | `PortfolioService.contributors` (from `VaRAnalytics.report` component VaR) |
| HTTP | `POST /api/v1/risk/contributors`; async `run_type=contributors` |
| RF-019 | `get_contributors` — `_execute_tool` returns **top 5** only |
| Args | Portfolio (bound). C1 may add `top_n` (extend schema) without changing ranking math. |
| Result | `Contributor {position_id, label, risk_amount, contribution_pct}` |
| Identities | Prefer RiskRun for C4; sync path has `portfolio_id` only. |
| Unit / sign | `risk_amount` = component VaR (currency loss). `contribution_pct` is **percent** (formatter uses `{:.1f}%`). |
| Errors | HEAVY refuse / 400 / 403. |
| Evidence | RF-019 `test_ai_query_orchestration.py`; contributors API tests. |

### compare_hedge (optional) — **reuse**

| | |
|---|---|
| Service | `PortfolioService.compare_scenarios` → `ScenarioComparisonEngine.compare` |
| HTTP | `POST /api/v1/risk/stress/formal/compare` (preferred wire); legacy `POST /risk/stress/compare`; `run_type=stress_compare` |
| Args | `portfolio`, `hedged_portfolio`, `scenarios` (min 1), `methodology` default `DELTA_GAMMA` |
| Result | `HedgeComparisonReport` |
| Identities | Shared **one** snapshot from the base book (`market_snapshot(base)`). |
| Unit / sign | `hedge_cost` = MV(hedged)−MV(base) (positive ≈ capital deployed). `var_improvement` / `es_improvement` = base−hedged (**>0 = risk reduced**). Per-scenario `improvement` = hedged_pnl−base_pnl; `loss = max(0, -pnl)`. |
| Errors | HEAVY / 400 / 422. |
| Evidence | `test_hedge_comparison.py`. |

### get_run_provenance (optional) — **reuse**

| | |
|---|---|
| Service | `RiskRunProvenance.from_risk_run` / `provenance_from_risk_run` |
| HTTP | `GET /api/v1/risk/runs/{run_id}/provenance` |
| Args | `run_id` |
| Result | `risk_run_id`, `portfolio_id` / `version`, `market_snapshot_id`, `as_of`, dataset id/version, `pricing_engine_version`, `methodology`, `scenario_set` / version, `calculation_config`, `duration_seconds`, `status`, optional `release_sha` |
| Identities | Lineage of one persisted run. |
| Unit / sign | None (metadata). |
| Errors | 404 run or provenance missing; 403 ACL. |

## Tools that must not exist

| Reject | Why |
|---|---|
| Shell / SQL / filesystem / general HTTP | Wave C non-goals; ADR 006. Yahoo/FRED stay behind catalog adapters. |
| MCP in C0 | C2 only. |
| Model-side VaR/ES/DV01/stress | ADR 006. Tool failure → typed error / clarification, never estimate. |
| Trade execution / advice | Architecture decision 7. |
| Second historical VaR engine | Reuse `HistoricalRiskEngine`. |
| Mapping `get_market_history` to Wave B analytics | Different domain (instrument levels vs portfolio wealth). |

## Error contract for C1

HTTP tools inherit `ErrorBody`:

| code | Typical HTTP | When |
|---|---|---|
| `validation_error` | 422 | Pydantic extra/type failures |
| `bad_request` | 400 | Dates, range, HEAVY refuse (`details.use=/risk/runs`), compare preconditions |
| `not_found` | 404 | Catalog miss, empty history, missing run |
| `forbidden` | 403 | RF-014 ACL |
| `unauthorized` | 401 | Token / provider authorization |
| `rate_limited` | 429 | Provider |
| `service_unavailable` | 503 | Provider unavailable |
| Series quality | 400 | `unsorted_dates`, `duplicate_dates`, `non_finite_value`, `non_positive_price`, `unknown_unit`, `insufficient_observations` |

RF-019 `validate_tool_call` refusals (keep for C3): unknown tool, empty tool name, JSON-schema failure. Prompt-injection keywords → `SAFE_UNGROUNDED_ANSWER` (no numbers).

## Provenance fields C4 will require

Every numeric C1 result should carry, from **existing** payloads where present:

- metric, value, unit, sign convention
- `risk_run_id` (or explicit “sync path has no run id” — C1 should prefer RiskRun)
- `as_of`, `market_snapshot_id`, `historical_dataset_id` / `version`
- methodology / scenario set

Gaps to close in **schema** (not new math): RF-019 sync tools and rates-showcase do not always stamp a caller RiskRun.

## Reuse evidence (existing tests; C0 did not change production code)

| Area | Tests |
|---|---|
| RF-019 / query | `backend/tests/test_ai_query_orchestration.py` |
| Catalog / search | `backend/tests/test_catalog_search.py` |
| Quality / history API | `backend/tests/test_quality_lineage.py`, `test_instrument_quality_api.py`, `test_quantlineage_product_api.py` |
| RiskRun | `test_risk_run_api.py`, `test_risk_run_spec.py`, `test_risk_run_lifecycle.py` |
| Compare / explain | Risk-run compare tests + flagship `RiskChangeReport` UI parse (`riskChangeReportSummary`) |
| KR-DV01 | `backend/tests/test_rates_showcase.py`, `test_sensitivities.py` |
| Hedge | `backend/tests/test_hedge_comparison.py` |
| Historical analytics (do not reuse as instrument history) | `backend/tests/test_historical_analytics.py` |

## Suggested C1 order

1. Freeze JSON schemas that **name** the services/routes above (allowlist only).
2. Prefer RiskRun-backed tools for any numeric portfolio/stress/contributor answer.
3. Alias or subset `compare_risk_runs` / `explain_risk_change` on **one** `compare_runs` engine.
4. Point `get_key_rate_dv01` at rates-showcase (USD 10Y row) unless Lead Architect approves wrapping `SensitivityEngine` for a caller book.
5. Do not implement MCP (C2), orchestration (C3), or UI (C5) in C1.

## Out of scope (reject if proposed)

MCP server, live LLM provider, shell/SQL/filesystem/HTTP tools, new VaR/stress/DV01 formulas, Wave B analytics as instrument history, marking G1 DONE from this inventory, production risk-math edits.
