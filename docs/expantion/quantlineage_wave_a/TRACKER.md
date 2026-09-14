# QuantLineage Wave A Tracker

Status values:
`NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `REVIEW`, `DONE`

Do not mark DONE without gate evidence.

| ID | Task | Status | Evidence / commit / tests | Blocker |
|---|---|---|---|---|
| A0.1 | Read decisions + inspect repo | DONE | Branch `feat/quantlineage-wave-a` @ `974798e`. Inspected MarketSnapshot, HistoricalMarketDataset/create_historical_dataset, HistoricalFactorPanel, RiskRun lineage, persistence, API errors, provenance, frontend api.js, CI. | |
| A0.2 | Record integration map | DONE | `docs/expantion/quantlineage_wave_a/A0_INTEGRATION_MAP.md` | |
| A1.1 | Inspect current boundaries | DONE | `docs/expantion/quantlineage_wave_a/A0_INTEGRATION_MAP.md` | |
| A1.2 | Normalized models | DONE | `eb134cb` `backend/app/market/ingestion/models.py` | |
| A1.3 | Provider protocols | DONE | `eb134cb` `backend/app/market/ingestion/protocols.py` | |
| A1.4 | Select equity/ETF provider | DONE | Yahoo public JSON + FRED. `docs/data_sources.md` | |
| A1.5 | Equity/ETF + FRED adapters | DONE | `yahoo.py` / `fred.py`; HTTP only in adapters + `http.py` | |
| A1.6 | Mock/fixture adapter tests | DONE | 42 passed `pytest tests/test_ingestion_*.py` (MockTransport) | |
| G1 | Provider/normalization gate | DONE | commit `eb134cb`; review PASS `.superpowers/sdd/task-g1-review.md`; no Critical/Important | |
| A2.1 | Canonical catalog model | DONE | `21d4c5d` `backend/app/market/catalog/` | |
| A2.2 | Curated supported universe | DONE | AAPL/MSFT/NVDA/SPY + DGS2/5/10; EURUSD omitted | |
| A2.3 | Catalog/search service | DONE | curated identity wins; unsupported caps false | |
| A2.4 | Instrument search API | DONE | `GET /api/v1/instruments/search`; empty → 200 `[]` | |
| A2.5 | Search UI | DONE | nav `market-data`; `MarketData.jsx` | |
| A2.6 | Search/capability tests | DONE | backend 27 + frontend 30 mocked | |
| G2 | Search gate | DONE | commit `21d4c5d`; review PASS `.superpowers/sdd/task-g2-review.md` | |
| A3.1 | Quality/lineage models | DONE | `1621251` `app.market.quality` | |
| A3.2 | Validation rules | DONE | unsorted/dup/non-finite/price/unit/min=5 | |
| A3.3 | Alignment policy | DONE | date intersection, no ffill | |
| A3.4 | Deterministic hashing | DONE | SHA-256 excludes retrieved_at | |
| A3.5 | Quality API/UI | DONE | `GET .../quality` + Inspect quality | |
| G3 | Quality/lineage gate | DONE | commit `1621251`; review PASS `.superpowers/sdd/task-g3-review.md` | |
| A4.1 | Dataset build spec | DONE | `real:public:wave-a`; mappings AAPL/MSFT/NVDA/SPY + DGS2/5/10; min aligned returns=5; `wave-a-v1` | |
| A4.2 | Equity level→return transform | DONE | `equity_relative_return`; 100→101 = +0.01 | |
| A4.3 | Rate percent→decimal/bp transforms | DONE | `percent_level_to_decimal` 4.25→0.0425; `percent_level_move_to_bps` 4.25→4.30 = +5 bp via `decimal_rate_to_bps` | |
| A4.4 | Freeze/materialization service | DONE | `freeze_public_history` → per-factor CSV + sidecar; G3 validate/align/hash; fakes only | |
| A4.5 | Existing dataset factory integration | DONE | `resolve_dataset_source` / `create_historical_dataset` load frozen CSV by id; demo remains default | |
| A4.6 | RiskRun dataset lineage | DONE | `dataset_identity` / `resolve_run_spec` persist sidecar id+content-hash version | |
| A4.7 | Quant mutation/regression tests | DONE | `tests/test_public_history_dataset.py` | |
| G4 | Public history gate | DONE | commit `0230c99`; review PASS `.superpowers/sdd/task-g4-review.md`; focused `calculate()` probe with adapters unloaded | |
| A5.1 | Snapshot build spec | DONE | `real:public:wave-a:{as_of ISO}:{content_hash}`; AAPL/MSFT/NVDA/SPY spots; DGS2/5/10 → USD 2Y/5Y/10Y; `rates[USD]`=DGS10 decimal; no public vol | |
| A5.2 | Public snapshot builder | DONE | `build_public_snapshot`; latest obs ≤ as_of; injected providers; lineage in persist meta | |
| A5.3 | 2Y/5Y/10Y rate mapping | DONE | `percent_level_to_decimal` 4.25→0.0425 on `key_rates`/`rates`; not bp | |
| A5.4 | Holiday/stale semantics | DONE | Monday as_of keeps Friday `source_observation_date`; `is_stale` fail-closed at 7 days | |
| A5.5 | Persist/bind snapshot | DONE | `persist_public_snapshot` then `bind_risk_run_to_saved_snapshot`; unsaved id refused | |
| G5 | Public snapshot gate | DONE | commit `4af0135`; review PASS `.superpowers/sdd/task-g5-review.md`; cash AAPL+MSFT priced from persisted Friday marks | |
| A6.1 | API contracts | DONE | history/datasets/snapshots dual-mounted; 1826-day bound; ErrorBody; no secrets | |
| A6.2 | History/data UI | DONE | Load History table + Freeze dataset + Build snapshot on Market Data (Wave A, not TSLA-only) | |
| A6.3 | Error UX | DONE | `err.body.code` + `err.body.message`; unavailable / rate_limited / stale / not_found / insufficient | |
| A6.4 | API/frontend tests | DONE | `tests/test_quantlineage_product_api.py` + MarketData/App vitest; fake providers; no live network | |
| A6.5 | Contract tests | DONE | search/history/quality/freeze/snapshot/failure covered with TestClient + MSW | |
| G6 | API/UI gate | DONE | commit `22be31a`; review PASS `.superpowers/sdd/task-g6-review.md` | |
| A7.1 | Demo materialization command | DONE | `scripts/build_public_demo_data.py`; injected fakes; `--live` opt-in in the script only | |
| A7.2 | Optional data-mode integration | DONE | `QUANTLINEAGE_DATA_MODE`; Compose unset; missing CSV fails closed naming freeze script | |
| A7.3 | Public demo docs | DONE | `docs/public_data_demo.md`; known_limitations + README pointer | |
| A7.4 | Optional T0/T1 real-date demo | DONE | `--t0/--t1` prints two snapshot ids + Friday lineage; existing `/risk/runs/compare` | |
| G7 | Public demo gate | DONE | commits `fd78bde` + `4c402d7`; review PASS `.superpowers/sdd/task-g7-review.md`; no Critical/Important | |
| A8.1 | Unit/date/missing attacks | DONE | `tests/test_wave_a_hostile.py`: as_of-before-history, Saturday last-print, UTC dates / `retrieved_at` | |
| A8.2 | Lineage/repro attacks | DONE | Canonical mapping + provider metadata fail-closed; snapshot id/as_of bind check; freeze→unload adapters→same RiskRun/hash/numbers | |
| A8.3 | Provider/security attacks | DONE | CI workflow parse offline; `YAHOO_BASE`/`FRED_BASE` constants; FRED key absent from 403/provenance; FX/vol N/A | |
| A8.4 | Full regression/CI | DONE | Local pytest **1749 passed**, 9 skipped. Frontend 165 + lint + build. GitHub CI `d73e7df` PR-FULL green: https://github.com/SergTogul/quantlineage/actions/runs/34728082547 | |
| A8.5 | Final hostile review | DONE | `reviews/wave-a-real-data-hostile-review.md`; G8 FAIL on red suite then fix `51b5869`; ruff `caad046`; mypy `d73e7df` | |
| G8 | Wave A final gate | DONE | commit `d73e7df`; CI green run 34728082547; red tests treated as blockers | |

## Completion summary
- Overall: `DONE` (G1–G8)
- Latest verified commit: `d73e7df`
- Latest green CI: https://github.com/SergTogul/quantlineage/actions/runs/34728082547
- Public providers chosen: Yahoo Finance public JSON (equity/ETF) + FRED (USD rates/macro)
- Frozen public dataset id/version: `real:public:wave-a` / SHA-256 of transformed panel + transform_config (not `retrieved_at`). Bytes live at `data/public_history/real-public-wave-a/<dataset_version>.csv` + sidecar; a later freeze with different content writes a new hash file and does not overwrite prior versions.
- Public snapshot id/as_of: `real:public:wave-a:{as_of ISO}:{content_hash}`; snapshot `as_of` is the requested date; lineage `source_observation_date` is last print ≤ as_of. Same calendar date with revised Yahoo/FRED marks gets a new id.
- Universe: US equity spots (AAPL/MSFT/NVDA/SPY) + USD Treasury key rates (DGS2/5/10). FX and vol remain outside Wave A public data.
- Hostile review verdict: PASS (`reviews/wave-a-real-data-hostile-review.md`); G8 closed after red-suite/CI lint blockers were fixed (`d73e7df`). Close-gate lineage holes (singleton CSV overwrite; as-of-only snapshot id) fixed before Wave B.
