# Wave B hostile review (G7 implementer)

Scope: prove Wave B analytics **cannot be disproved** on the mandatory B7 attacks (units, annualization, signs, beta denominator, TE, P&L vs loss, KR vs parallel DV01, benchmark alignment, stale UI, hidden residual, client-side risk math). Frozen panel + snapshot identity drive Historical Analytics. Charts copy API fields.

This is the implementer artifact. Independent review still applies. G7 is **not DONE**. A red test is a blocker, never “residual.”

## 1. Blockers

None on the Wave B analytics path after the smallest UI close-gate fix.

Attacks that failed closed after the smallest production fix (no new product scope):

- **Stale async UI response.** Historical Analytics kept the previous range’s summary/charts on screen after start/end changed, while a newer POST was in flight. Identity (`result.start` / `result.end`) disagreed with the date controls. A slower first response was already ignored via `seq` + `cancelled` (that pin passed). The in-flight previous result did not. Now a result or error is shown only when its portfolio id/version + start + end match the request that is on the controls. Cited: `test_does_not_keep_the_previous_range_result_on_screen_while_a_newer_request_is_in_flight` (red, then green), `test_does_not_apply_a_slower_first_response_after_a_later_range_request`.
- **CI golden-demo e2e strict locator.** Independent G7 review: `flagship.getByText(/Market/)` matched both identity **Market snapshot** and totals **Market $0** (`e2e-playwright` red, run 34733596657). Waterfall steps now have unique `waterfall-step-{key}` testids; the e2e asserts those plus exact `Market snapshot`. Not a math hole. Cited: `keeps Market snapshot identity distinct from the waterfall market step`.

## 2. High severity

Closed in this change:

- **In-flight previous Historical Analytics result.** Range change left `2.48%` / old identity visible. Display is now keyed (`requestKey` / `resultRequestKey`). Waiting copy shows until the matching POST returns.

No remaining high-severity unit, annualization, beta-inversion, TE, drawdown-sign, VaR-loss, residual-hidden, or client-recompute issue on the named attacks after the pins below.

## 3. Medium/low worth fixing

G1–G6 ledger (not reopened unless they fail a named attack — they did not, except stale UI):

- Sharpe **unit cell** still copies `units.volatility` (`annualized_fraction`) when Sharpe is defined. The value itself is `formatNumber` (not ×100). Backend `units` has no `sharpe` key. Display bug, not a percent/fraction math failure.
- `formatFraction` always ×100 for labeled fraction fields. Hostile percent/fraction pin is `0.0248` → `2.48%` with unit `fraction`. Not a second CAGR engine.
- `compute_historical_analytics` defaults `methodology=LINEAR`; HTTP request defaults `DELTA_GAMMA`. Callers that omit methodology disagree. Not a named B7 attack.
- n&lt;2 sample vol is `0.0` + note, Sharpe `None` (already pinned).
- `risk_free_rate` unit is implicit (same fraction as CAGR). Default `0`.
- Date-intersection for SPY inside `compute()` is applied to a rectangular panel (`spy_dates == portfolio_dates`). Shifted-date protection is the helper `align_dated_series` used by the compute path; the distinguishing zip-vs-intersection case is pinned on that helper.
- VaR/ES trend skipped in B3 (no stored RiskRun time series). N/A for this matrix.
- Historical Analytics is HEAVY and is not a RiskRun type. Compose `RISKFORGE_EXTERNAL_WORKER=1` 400s the page (demo script uses in-process uvicorn).
- Frontend `eslint` `react-hooks/set-state-in-effect` in `Analytics.jsx` (pre-existing; not Wave B math).

## 4. Rejected false positives

- **Bar width / SVG Y scale is “risk math.”** `contributionBarPct` and `datedSeriesChart` scale `|API amount| / maxAbs` and min/max of the payload for layout. Not VaR, vol, or drawdown. Cited: `frontend/src/lib/riskVisuals.test.js`.
- **Display `%` means the backend stored percents.** Backend stores fractions (`0.01 = 1%`). UI `formatFraction` is labeled formatting. Cited: `test_percent_fraction_units_beta_te_excess_not_scaled_by_100`, `renders fixture fractions with unit labels, not bare 2.48`.
- **Identical series ⇒ beta=1 does not prove the denominator.** A doubled portfolio series would also be beta=1 under several wrong formulas. The distinguishing pin is `r_p = 2 r_b` ⇒ beta=2, not `cov/var(r_p)` = 0.5. Cited: `test_beta_denominator_is_cov_over_var_benchmark_not_inverted`.
- **Shifted-date helper unused.** `_canonical_benchmark_relative_risk` calls `align_dated_series` (`historical_analytics.py` ~316). Rectangular panels make the intersection the full window; the helper still rejects zip/ffill when dates differ.
- **Zero residual hidden by CSS.** Residual step is always in the waterfall list; `residual === 0` still shows `$0`. Cited: `keeps the residual label visible when residual is 0`.
- **Stress `-$9.0K` should be positive loss.** Stress heatmap is scenario **P&L** (`pnl: -9000`). VaR/ES are currency **loss** (`max(0, quantile(-pnl))`). Different conventions, both labeled.
- **Frontend `* 100` is CAGR.** `formatFraction` does not use `periods_per_year` or `**`. Source pin forbids `Math.sqrt`, `quantile`, `** (`.

## 5. Verification evidence

### Named attack → status, file:line, pin

| Attack | Status | Code | Pin |
|---|---|---|---|
| percent/fraction | **held** | `historical_analytics.py` 13–17, 447, 563–569; `HistoricalAnalytics.jsx` `formatFraction` 18–21 | `test_percent_fraction_units_beta_te_excess_not_scaled_by_100`; `test_constant_returns_compound_wealth_and_cagr`; HA `renders fixture fractions…` (`0.0248` → `2.48%`, unit `fraction`) |
| CAGR/vol annualization | **held** | CAGR `457`; vol `463–465` (`std × sqrt(ppy)`); convention `69–77` | `test_constant_returns_compound_wealth_and_cagr`; `test_annualization_periods_per_year_scales_cagr_and_vol`; `test_rolling_vol_uses_sample_std_times_sqrt_periods_per_year` |
| drawdown sign | **held** | `473–475` (`W/peak - 1`, implicit `W_0=1`, ≤ 0) | `test_known_drawdown_uses_implicit_unit_nav_peak` (max DD ≈ `-0.19`); HA `charts API drawdown values that are ≤ 0` (`[0, -0.083, -0.02]`) |
| Sharpe zero-vol | **held** | `467–469` → `None` + `sharpe_undefined_zero_volatility` | `test_zero_vol_constant_returns_leaves_sharpe_undefined`; `test_short_window_one_observation_defines_return_not_sample_vol`; HA `shows Sharpe as undefined when the API returns null, not zero` |
| beta denominator | **held** | `321–325` `cov / var_b`; zero `var_b` raises | `test_beta_denominator_is_cov_over_var_benchmark_not_inverted` (2× series → 2, not 0.5); `test_identical_series_beta_one_tracking_error_zero`; `test_zero_benchmark_variance_fails_closed` |
| tracking-error annualization | **held** | `329` `std(r_p-r_b, ddof) × sqrt(ppy)` | `test_tracking_error_annualizes_std_times_sqrt_periods_per_year` (ppy=12, not 252, not ×12); `test_percent_fraction_units_beta_te_excess_not_scaled_by_100` |
| P&L vs loss | **held** | HA VaR/ES from `HistoricalRiskEngine.calculate` (`504–514`, `550–552`); engine `losses = -pnl` (`historical.py` 581–583); stress heatmap API `pnl` | `test_var_es_tail_reuses_historical_risk_engine`; `test_benchmark_var_es_reuses_historical_risk_engine_on_spy_book`; RiskVisuals `labels scenario P&L from API pnl, not inverted loss` |
| bp vs currency | **held** | KR-DV01 from `key_rate_dv01`; Parallel DV01 from `parallel_dv01`; labels not mixed (`Analytics.jsx` 117–118, `RiskVisuals.jsx` 39) | `charts API key_rate_dv01 by tenor and labels parallel DV01 separately`; source pin no `key_rate_dv01 +` / `0.0001` |
| benchmark date mismatch | **held** | `align_dated_series` 175–206: calendar intersection, no zip, no ffill; overlap &lt; 2 fails | `test_shifted_dates_are_not_silently_matched`; `test_insufficient_overlap_fails_closed`; `test_missing_spy_factor_fails_closed`; `test_missing_weekday_drop_with_note_does_not_ffill` |
| stale async UI response | **failed-closed** (this change) | `HistoricalAnalytics.jsx` `requestKey` 39–50, `current`/`errorCurrent` 182–185, apply 194–205 | RED then GREEN: `does not keep the previous range result…`; GREEN: `does not apply a slower first response…` |
| hidden residual | **held** | `riskChangeWaterfallSteps` always includes residual (`riskVisuals.mjs` 112–117); DOM `waterfall-step-residual` | `riskChangeWaterfallSteps copies API fields and keeps residual at 0` (reconstructed residual ≠ 0, UI keeps 0); `keeps the residual label visible when residual is 0` |
| frontend financial recomputation | **held** | HA formats/charts only; waterfall copies API fields; bars copy `risk_amount` / `contribution_pct` | Source pins in `HistoricalAnalytics.test.jsx`, `riskVisuals.test.js`, `RiskVisuals.test.jsx`, `RiskChangeAttribution.test.jsx` (no `quantile` / `Math.sqrt` / `** (` / `total_change -` / `previous_risk +`) |

### Gaps closed this gate

| Gap | Test |
|---|---|
| beta could be inverted (`cov/var(r_p)` or `var(r_b)/cov`) | `test_beta_denominator_is_cov_over_var_benchmark_not_inverted` |
| TE stuck at 252 or linear ×ppy | `test_tracking_error_annualizes_std_times_sqrt_periods_per_year` |
| Slower first HA POST overwrites later range | `does not apply a slower first response after a later range request` |
| Previous HA result shown for a new range | `does not keep the previous range result on screen while a newer request is in flight` |

## 6. Final verdict

**PASS (Wave B matrix), with the stale-UI close-gate item now fixed.** Independent review must still run. G7 stays **NOT_STARTED** until that review **and** CI green.

No remaining named-attack blocker on percent/fraction, CAGR/vol, drawdown sign, Sharpe zero-vol, beta denominator, TE annualization, P&L vs loss, KR vs parallel DV01, benchmark intersection, hidden residual, or client risk math. Historical Analytics no longer presents a prior range as if it belonged to the current POST.

Do **not** treat Wave B as a live-data product. Inputs are the frozen panel + snapshot already bound to the service. Do not treat public-data mode as covering the full cross-asset derivatives book.

Do not mark G7 DONE from this implementer report.
