# Agent Handoff — M4.7

## Task
M4.7 Key-rate DV01 limit drill-down contributors use tenor KR DV01 (not parallel `dv01`)

## Owner
Portfolio Risk Engineer

## Summary
`contributors_for_metric("key_rate_dv01")` no longer maps to Valuation `dv01`. It uses `SensitivityEngine` on the same binding pillar as `LimitEngine` (`max_T |portfolio KR_T|`), ranks positions by abs tenor KR, and falls back to parallel bump-revalue when no key-rate measures exist (same as `_key_rate_dv01_abs`).

## Files changed
- `backend/app/risk/limit_drilldown.py`
- `backend/tests/test_limit_drilldown.py`
- `ROADMAP.md` (M4.7 DONE; residual closed; M12.6 KR note removed — may already be on HEAD via prior commit)
- `docs/agents/HANDOFF_M4_7.md`

## Public/interface changes
- Optional `market: MarketSnapshot | None` on `contributors_for_metric` (defaults None; engine path unchanged).
- No API / DTO / PricingEngine seam changes.

## Numerical conventions
- Units: per-bp P&L (same as `SensitivityEngine` key_rate_dv01 / LimitEngine).
- Sign: ranking uses abs; signed position KR on binding pillar sums to portfolio binding measure.
- Tolerances: contribution shares abs 1e-9; signed KR reconcile rel 1e-9 / abs 1e-6.

## Tests added/updated
- `test_key_rate_dv01_contributors_use_binding_tenor_not_parallel_dv01`
- `test_key_rate_dv01_contributors_fallback_matches_parallel_without_key_rates`
- `test_key_rate_dv01_limit_value_matches_binding_pillar_abs`

## Commands executed
```bash
cd backend && .venv/bin/python -m pytest tests/test_limit_drilldown.py tests/test_limits.py -q --tb=short
```

## Results
- Backend: **19 passed**, 1 Starlette/httpx deprecation warning
- Frontend / QuantLib / C++ / Build: not in scope

## Known limitations / risks
- Default `PositionMarketDataProvider` snapshots still omit `key_rates` / curves; production path uses parallel fallback until market data attaches pillars (then tenor KR activates automatically).
- Binding pillar is max |portfolio KR|; multi-pillar limit regimes are out of scope.

## Follow-up / next owner
- Owner: Market Data & Curves (optional) — attach standard key_rates/curves on snapshots so KR limits/drill-down are tenor-true by default.
- Blocking?: no
