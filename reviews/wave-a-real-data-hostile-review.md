# Wave A hostile review (G8 implementer)

Scope: prove Wave A cannot be disproved on units, dates, missing data, lineage, provider failures, secrets/SSRF, or reproducibility. Synthetic demo still works. Frozen public data drives existing risk with network disabled. CI workflows stay offline.

This is the implementer artifact. G8 stays `IN_PROGRESS` pending independent review. No GitHub CI claim.

## 1. Blockers

None on the Wave A public-data path.

Attacks that failed closed after the smallest production fixes (no new product scope):

- Freeze previously accepted a window **before** any observation and wrote future prints. Now `MissingRequiredFactorError`.
- `real:public:wave-a` freeze with DGS10→`EquitySpot` or AAPL→`RateZero:USD:10Y` now raises `FreezeError` (`canonical mapping mismatch`).
- Series whose `metadata.source` / `source_symbol` disagrees with the locked mapping now fails freeze/snapshot.
- Snapshot id `real:public:wave-a:{as_of}` with a swapped date cannot persist or bind (`MismatchedPublicSnapshotIdentityError`).

## 2. High severity

None remaining on Wave A units, lineage, secrets, SSRF, or freeze→offline RiskRun identity.

## 3. Medium/low worth fixing

G1–G7 ledger (not reopened as implementation work):

- G7: module `public_demo.main()` ignores `--live`; repo-root shim is the live gate. Freeze report omits CSV path. `--output *.csv` is a directory hint. T0/T1 default freeze window is the full Wave A spec.
- G7: `QUANTLINEAGE_DATA_MODE=synthetic` is now pinned (`test_explicit_synthetic_data_mode_keeps_demo_dataset`); unset vs explicit synthetic were already the same code path.
- G6 leftover: `GET /market/history/{instrument_id}`, `GET /market/snapshots/{snapshot_id}`, `POST /market/snapshots/from-public-data` are missing from `ENDPOINT_EXECUTION_CLASS` (`test_every_owned_route_is_classified`).
- G1 session coupling: `test_importing_quant_core_does_not_load_adapter_modules` deletes `app.risk.*` / `app.pricing.*` and reimports them. Later tests in the **same** pytest process then compare split `RateZero`/`EquitySpot` class identities (`isinstance` fails). Isolated, those later tests pass. Not a public-data math bug.
- Frontend `eslint` `react-hooks/set-state-in-effect` in `Analytics.jsx` (pre-existing; not Wave A).

## 4. Rejected false positives

- **FX inversion / EURUSD.** Wave A has no FX pair. Cited: `test_wave_a_universe_is_locked_and_omits_eurusd`, `test_wave_a_spec_locks_factor_mappings_and_identity`, `test_public_paths_emit_no_fx_or_fred_vol_surface`. Not a missing FX product.
- **Vol fraction vs percent.** Public snapshot/history has no FRED vol surface. Cited: `test_prices_cash_aapl_book_from_public_snapshot_without_provider` (empty `equity_vols` / `vol_surfaces`) and `test_public_paths_emit_no_fx_or_fred_vol_surface`.
- **Monday as_of using Monday’s date as the print.** Lineage keeps Friday. Extra Saturday as_of also keeps Friday (`test_saturday_as_of_keeps_friday_last_print`).
- **`retrieved_at` shifting the observation calendar date.** Observation dates are UTC calendar dates; `retrieved_at` on the next day does not change `source_observation_date`.
- **Full-repo pytest red ⇒ Wave A numbers are wrong.** Failures after G1 isolation reload are split dataclass identity, not Yahoo/FRED transforms. Wave A hostile + G4/G5/G7 targeted files pass when that reload is not sequenced immediately before demo/pricing tests.
- **API imports `YahooFinanceAdapter` so default demo is live.** Request-time Depends; factory/demo path does not import adapters (`test_default_data_mode_unset_does_not_import_or_call_yahoo`, `test_explicit_synthetic_data_mode_keeps_demo_dataset`).
- **“CI is green” means GitHub PR-FULL.** This review does not claim a pushed PR. Offline workflow assertions plus local commands only.

## 5. Verification evidence

### 09 attack → existing test (not rewritten)

| Attack | Evidence |
|---|---|
| Rate % / decimal / bp; equity 100→101; 4.25→0.0425; 4.25→4.30 = +5 bp | `test_public_history_dataset.py`, `test_public_market_snapshot.py` |
| Adjusted vs unadjusted | `test_yahoo_history_uses_adjusted_close_not_raw_close` |
| Duplicate / unsorted / non-finite / min obs / stale 7d | `test_quality_lineage.py` |
| Alignment intersection, no ffill, overlap below min | `test_quality_lineage.py` |
| Missing entire factor | `test_missing_required_factor_fails_freeze` |
| Same content same hash; one value → new hash; `retrieved_at` excluded | `test_content_hash_ignores_retrieved_at`, `test_same_normalized_content_same_hash_changed_observation_new_hash` |
| RiskRun dataset id/version | `test_riskrun_factory_identity_matches_frozen_artifact` |
| Monday as_of / Friday print; stale fail-closed snapshot | `test_monday_as_of_keeps_friday_source_observation_date`, `test_stale_series_fails_closed_and_does_not_use_old_print` |
| Timeout / 429 / 401/403 / 404 / malformed / empty | `test_ingestion_yahoo.py`, `test_ingestion_fred.py` |
| Adapters not imported by quant core | `test_ingestion_isolation.py` + G4/G5 isolation |
| FRED key not in search/history/quality JSON | catalog + `test_quantlineage_product_api.py` |
| Default factory demo; compose not public | `test_public_data_demo.py` |
| EURUSD omitted | `test_wave_a_universe_is_locked_and_omits_eurusd` |
| No public vol | G5 snapshot builder; `test_public_paths_emit_no_fx_or_fred_vol_surface` |

### Gaps closed (A8.1–A8.3) — `tests/test_wave_a_hostile.py`

| Gap | Test |
|---|---|
| as_of before history | `test_snapshot_as_of_before_history_fails_closed_and_does_not_invent_print`, `test_freeze_end_before_history_fails_closed` |
| Extra holiday/weekend | `test_saturday_as_of_keeps_friday_last_print` |
| Timezone / date | `test_retrieved_at_next_calendar_day_does_not_shift_observation_date`, `test_yahoo_unix_timestamps_are_utc_calendar_dates_not_local_tz` |
| Wrong canonical mapping | `test_mapping_dgs10_onto_equity_spot_cannot_freeze_wave_a`, `test_mapping_aapl_onto_rate_zero_cannot_freeze_wave_a` |
| Metadata vs content provider | `test_series_provider_metadata_mismatch_fails_freeze`, `test_series_source_symbol_mismatch_fails_snapshot` |
| Snapshot id vs as_of | `test_swapped_snapshot_id_date_must_not_bind` |
| Freeze → adapters unloaded → same RiskRun/lineage/numbers | `test_freeze_then_adapters_unloaded_same_riskrun_lineage_and_numbers` |
| CI workflows offline | `test_ci_workflows_stay_offline` |
| SSRF hardcoded bases | `test_yahoo_and_fred_bases_are_hardcoded_module_constants` |
| Secrets in exceptions / provenance | `test_fred_key_absent_from_403_freeze_snapshot_and_provenance` |
| FX / vol N/A | `test_public_paths_emit_no_fx_or_fred_vol_surface` |

Repro (mandatory 09): freeze with fakes → drop `yahoo`/`fred` from `sys.modules` and block `httpx.Client.request`/`send` → `create_historical_dataset("real:public:wave-a")` + bind/price G5 cash AAPL+MSFT book → **same** `dataset_id` / `dataset_version`, snapshot `id` / `content_hash()`, market values, and `var_95` / `var_99` / ES.

### Commands (local; not pushed)

```text
cd backend
PYTHONPATH=. .venv/bin/python -m pytest -q --tb=short \
    tests/test_ingestion_*.py \
    tests/test_quality_lineage.py \
    tests/test_catalog_search.py \
    tests/test_public_history_dataset.py \
    tests/test_public_market_snapshot.py \
    tests/test_public_data_demo.py \
    tests/test_quantlineage_product_api.py \
    tests/test_ingestion_isolation.py \
    tests/test_demo_historical_dataset.py \
    tests/test_wave_a_hostile.py
# 164 passed, 2 failed: demo dataset tests immediately after isolation reload
# (split RateZero identity). Same two tests: 2 passed in a fresh process.

PYTHONPATH=. .venv/bin/python -m pytest -q --tb=line
# 251 failed, 1496 passed, 9 skipped — cascade after G1 isolation reload
# plus G6 unclassified /market/history and /market/snapshots routes.

PYTHONPATH=. RISKFORGE_REQUIRE_QUANTLIB=1 RISKFORGE_PRICING_ENGINE=quantlib \
  .venv/bin/python -m pytest -q --tb=short \
  tests/test_quantlib_golden.py tests/test_quantlib_pricing.py \
  tests/test_quantlib_process_state.py tests/test_curve_pricing.py \
  tests/test_var_es_golden.py tests/test_approx_pnl_units_golden.py \
  tests/test_full_reval_golden.py tests/test_quantlib_gate.py
# 134 passed (QuantLib 1.43)

cd ../frontend && npm test     # 165 passed (23 files)
cd ../frontend && npm run lint # fail: pre-existing Analytics.jsx setState-in-effect
cd ../frontend && npm run build # ok (vite)

cd ../e2e && npm test
# skip: Playwright launched Chrome; sandbox kill EPERM (browsers exist)

scripts/smoke_postgres.sh
# skip: RISKFORGE_DATABASE_URL unset. SQLite persistence tests are in backend pytest.

ruff check tests/test_wave_a_hostile.py tests/test_public_data_demo.py \
  app/market/history/spec.py app/market/history/freeze.py app/market/history/snapshot.py
# All checks passed
```

CI workflows (`.github/workflows/ci.yml`, `nightly.yml`) contain no `--live`, `QUANTLINEAGE_DATA_MODE=public`, `FRED_API_KEY`, `query1.finance.yahoo.com`, or `api.stlouisfed.org` in job env/steps.

## 6. Final verdict

**PASS (Wave A matrix).** Independent review must still run.

No remaining unit/lineage/reproducibility blocker on public freeze/snapshot. No FRED key in 403/provenance. Synthetic demo remains the default (`QUANTLINEAGE_DATA_MODE=synthetic` or unset). Frozen public CSV + persisted snapshot drive existing `HistoricalRiskEngine` / builtin pricing with adapters unloaded. Workflows are offline.

Do **not** treat GitHub PR-FULL as green (not pushed). Do **not** treat the 251 full-suite failures as Wave A transform defects; they are G1 module-reload class identity plus G6 route-map leftovers. G8 is not marked DONE.
