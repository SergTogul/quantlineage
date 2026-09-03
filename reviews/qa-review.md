# RiskForge QA Review

Independent test-quality review. No application, test, CI, roadmap, or dependency files were modified.

Review date: 2026-09-03. Workspace: `/Users/user/src/riskforge-mvp`. QuantLib 1.43 and `g++` (Apple clang 14.0.3) were available locally.

## Executive Summary

Quality confidence rating: **6/10**

The suite is large, mostly green, and stronger than a typical MVP on **pricing properties, snapshot immutability, hierarchy additivity, attribution reconciliation, crisis-library labeling, native kernel parity, and deterministic seeds**. That volume does **not** currently prove that Historical VaR/ES select the loss tail correctly, that approximate P&L units cannot silently scale by 100×, or that CI always executes the QuantLib production adapter.

The highest-value question this review answers: **a wrong-tail or off-by-one Historical VaR implementation can remain green** because almost every VaR/ES test asserts only `ES ≥ VaR ≥ 0` ordering, not an exact quantile on a known P&L series.

Executed baseline:

- Backend: `cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=quantlib .venv/bin/python -m pytest -q` → **659 passed**, 0 failed, **0 skipped**, 0 xfailed, 1 Starlette/httpx deprecation warning, 36.38s. Collect-only: **659 tests**. QuantLib adapter tests executed (not skipped). Native kernel tests compiled and ran (`g++` present).
- QuantLib: Installed **1.43**. `tests/test_quantlib_golden.py` **54 tests**, `tests/test_quantlib_pricing.py` **17 tests**, plus QL cases in curve/surface pricing. File-level `pytest.importorskip("QuantLib")` did not skip in this environment. `conftest.py` still defaults `RISKFORGE_PRICING_ENGINE=builtin` via `setdefault` when the env var is unset.
- Frontend: `cd frontend && npm test` → **74 passed** (8 files). `npm run build` → **OK** (Vite; `dist/assets/index-D0rofwo0.js` 253.11 kB). `npm run lint` → **OK** (`eslint src --max-warnings 0`).
- Frontend build: **passed** (see above).
- Native C++: `g++ -std=c++20 -O2 -pthread -I native/include native/tests/kernel_test.cpp` → printed `risk_kernel_ok`. Shared lib built. Pytest `test_native_kernel.py` / `test_historical_scenario_kernel.py` included in the 659.
- E2E: `cd e2e && npm test` (Playwright **Chrome channel**, builtin engine) → **12 passed** in 32.5s. A first attempt with `PLAYWRIGHT_USE_CHROMIUM=1` failed: Playwright **does not support bundled Chromium on macOS 13**; CI uses Ubuntu Chromium (`install:browsers:ci`). Local README is accurate that Chrome channel is required on this host.
- Static analysis: `ruff check app tests` → **All checks passed**. `mypy app` → **Success: no issues found in 82 source files**. Both gates are **staged** (many Ruff ignores; mypy `disable_error_code` includes `arg-type`, `assignment`, `var-annotated`, `no-redef`, `misc`). Postgres smoke script was **not** re-run (Docker); CI job `postgres-persistence-smoke` exists.

Finding counts:

- Critical: **1**
- High: **10**
- Medium: **10**
- Low: **5**

Top escaped-defect risks:

1. Historical VaR/ES computed on the **profit** tail or with a **wrong percentile** still satisfy `ES ≥ VaR99 ≥ VaR95 ≥ 0`.
2. Approximate VaR **vol-point** (`×100`) or **DV01×bp** scaling is wrong while kernel-vs-NumPy parity and ES ordering still pass.
3. CI remains green if the QuantLib wheel fails to install (`RISKFORGE_PRICING_ENGINE=builtin`; QL tests `importorskip`).
4. `VaRAnalytics` LINEAR/DELTA_GAMMA **ignores** a provided `MarketSnapshot`; Greeks come from trade-local marks.
5. Scenario Builder / reverse-stress **percent → fraction** lives only in helper unit tests; component and E2E would still show a “Loss” if the widget sent raw `20` instead of `0.20`.

## Test Coverage Matrix

Implementation = what exists in code. Test Coverage = how well tests defend financial meaning. Confidence = reviewer’s confidence in that rating.

| Capability | Implementation | Test Coverage | Confidence | Notes |
|---|---|---|---|---|
| Equity pricing | Implemented | GOOD | HIGH | `value = qty × spot`; snapshot override in adapters. |
| Equity futures | Implemented | GOOD | HIGH | CIP identity includes `quantity × multiplier`; QL vs Builtin. |
| Equity options | Implemented | GOOD | HIGH | BS golden, unit-delta bounds, discounted intrinsic, FD Greeks. Missing strike/vol monotonicity properties. |
| Bonds | Implemented | GOOD | HIGH | Yield-up → price-down property; DV01 sign; continuous ZC vs QL. |
| Swaps | Implemented | PARTIAL | HIGH | Payer sign/monotonicity strong; QL vs Builtin NPV **not** identical (documented &lt;50bp of notional). |
| FX forwards | Implemented | GOOD | HIGH | CIP algebra; FX delta ≈ notional×spot; snapshot override. |
| FX options | Implemented | GOOD | HIGH | Independent GK golden; vega/delta vs Builtin. |
| Rate futures | Implemented | GOOD | MEDIUM | Algebraic STIR mark; exact DV01 in builtin test; not a full QL FRA. |
| Caps/floors | Implemented (scoped Black-76) | GOOD | HIGH | Independent Black-76 strip reference; QL no-fallback. |
| Swaptions | Implemented (scoped Black-76) | GOOD | HIGH | Independent Black-76; payer/receiver; QL no-fallback. |
| Market snapshots | Implemented | GOOD | HIGH | Frozen + nested freeze; bump/apply/diff; content_hash. |
| Equity spots | Implemented | GOOD | HIGH | Relative bump; symbol-specific override (`NVDA` only). |
| Rates / curves | Implemented | GOOD | HIGH | Parallel vs tenor isolation; curve pricing tests. |
| FX spots | Implemented | GOOD | HIGH | Relative bump; CIP. |
| Vol / vol surfaces | Implemented | GOOD | HIGH | Grid shocks; surface vs scalar; QL surface-not-constant-vol guards. |
| Snapshot bumping | Implemented | GOOD | HIGH | Typed factors; vol rewrites attached grids. |
| Snapshot diffing | Implemented | GOOD | MEDIUM | Present; less emphasis than bump/apply. |
| Historical observations | Synthetic + packaged CSV | GOOD | HIGH | Seeded RNG continuity; CSV columns; honest synthetic labeling. |
| Equity spot factor | Implemented | GOOD | HIGH | Typed taxonomy tests. |
| Equity vol factor | Implemented | GOOD | HIGH | |
| Rates / key-rate | Implemented | GOOD | HIGH | Tenor isolation when key_rates present; parallel fallback flagged. |
| FX spot factor | Implemented | GOOD | HIGH | |
| Typed factor taxonomy | Implemented | GOOD | HIGH | `test_factor_types.py`. |
| Delta | Implemented | GOOD | HIGH | Analytic, FD, portfolio sum-by-symbol. |
| Gamma | Implemented | GOOD | HIGH | FD vs analytic; option-only. |
| Vega | Implemented | GOOD | HIGH | Per vol point; FD `×0.01`. |
| DV01 | Implemented | GOOD | HIGH | Sign + FD vs analytic (~25% band on duration bond). |
| Key-rate DV01 | Implemented | GOOD | HIGH | 10Y vs 2Y isolation. |
| FX delta | Implemented | GOOD | HIGH | FD vs analytic; golden notional×spot. |
| Historical VaR | Implemented | WEAK | HIGH | Ordering/determinism only; **no exact quantile**. |
| Parametric VaR | Implemented | PARTIAL | HIGH | Euler allocation tested; not a separate golden σ. |
| Full-revaluation VaR | Implemented | PARTIAL | HIGH | “Differs from linear”; zero-shock; not a 1-name exact P&L series. |
| Linear VaR | Implemented | PARTIAL | HIGH | Gamma omitted vs Δ-Γ; no magnitude pin. |
| Delta-gamma VaR | Implemented | PARTIAL | HIGH | Default path; seeded “regression” does not pin numbers. |
| Expected Shortfall | Implemented | PARTIAL | HIGH | `ES ≥ VaR`; contribution recon; no exact tail mean. |
| Component VaR | Implemented | PARTIAL | HIGH | Reconciles to **parametric** VaR, not historical quantile. |
| Marginal VaR | Implemented | GOOD | HIGH | Equals component at unit weights; FD check. |
| Incremental VaR | Implemented | GOOD | HIGH | `after − before`; no mutate base; add/remove. |
| What-if risk | Implemented | GOOD | HIGH | API + helper; invalid ops rejected. |
| Predefined scenarios | Implemented | GOOD | HIGH | Library + threat ranking. |
| Custom scenarios | Implemented | GOOD | MEDIUM | API contract; threshold breach; weak QL `!=` smoke. |
| Multi-factor scenarios | Implemented | PARTIAL | HIGH | Snapshot apply pins all factors; P&L recon uses interaction residual. |
| Reverse stress | Implemented | GOOD | HIGH | Converge / no-solution / bp wire units / determinism. |
| Scenario comparison | Implemented | GOOD | HIGH | Hedge report metrics; identical books → zero delta. |
| Hedge comparison | Implemented | GOOD | HIGH | Cost, VaR/ES improvement identities; base not mutated in UI helper. |
| Contribution decomposition | Implemented | PARTIAL | HIGH | Hierarchy sums exact; factor path can hide a dropped shock in residual. |
| Portfolio aggregation | Implemented | GOOD | HIGH | PV = sum of trades (property). |
| Desk / strategy / book / trade | Implemented | GOOD | HIGH | Placement + additive Greeks/MV/stress; VaR recomputed not summed. |
| Market attribution | Implemented | GOOD | HIGH | Identical state → 0; delta 1% equity = 100. |
| Risk-change attribution | Implemented | PARTIAL | MEDIUM | Backend tests exist; UI is MSW/E2E display. |
| P&amp;L explain | Implemented | GOOD | HIGH | Drivers + residual identity; Taylor band on options. |
| Residual reconciliation | Implemented | GOOD | HIGH | `explained + residual = actual`. |
| New / closed trades | Implemented | GOOD | MEDIUM | Quantity change → “New trades”; closed covered in attribution module. |
| Limit calculation | Implemented | GOOD | HIGH | Status mapping 80 / 100 / 100.01. |
| Warning / breach | Implemented | GOOD | HIGH | Inclusive warning; strict `>` breach. |
| Limit drill-down | Implemented | GOOD | MEDIUM | Dedicated tests; contributors. |
| API | Implemented | PARTIAL | HIGH | Dual-mount, typed models, errors; dashboard smoke is shape-only. |
| Persistence | Implemented | PARTIAL | HIGH | SQLite unit + worker claim; Postgres is CI smoke, not pytest. |
| Risk runs | Implemented | GOOD | HIGH | QUEUED/RUNNING/COMPLETED; external worker flag. |
| Async worker | Implemented | GOOD | HIGH | `claim_queued` / poll_once / SKIP LOCKED documented. |
| Caching | Implemented | GOOD | HIGH | Hit/miss; market bump invalidation; config key; conftest resets LRUs. |
| Python/C++ parity | Implemented | GOOD | HIGH | Distinct Greek columns; 32×64 matrix; NumPy vs kernel. |
| Native bounds / empty | Implemented | GOOD | HIGH | Empty, single shock, zeros, NaN propagate. |
| Native large arrays | Implemented | PARTIAL | MEDIUM | 32×64 and 256 shocks; not 10k×1k correctness (bench only). |
| Dashboard | Implemented | PARTIAL | HIGH | E2E smoke + lib formatters; no numeric VaR assert. |
| Risk factors UI | Implemented | PARTIAL | MEDIUM | Display helpers; little RTL. |
| VaR / ES UI | Implemented | PARTIAL | HIGH | E2E loads panels; no magnitude. |
| Stress UI | Implemented | PARTIAL | HIGH | Scenario builder E2E; conversion only in `scenarioPayload` unit test. |
| Scenario builder | Implemented | PARTIAL | HIGH | Helper conversion GOOD; component/E2E do not capture request body. |
| Reverse stress UI | Implemented | PARTIAL | HIGH | `% → fraction` helper tested; E2E checks “Required equity shock” text. |
| Hierarchy UI | Implemented | PARTIAL | HIGH | Tree-walk unit tests; no RTL drill. |
| Attribution UI | Implemented | PARTIAL | MEDIUM | Display parse; E2E residual text. |
| Limits UI | Implemented | GOOD | HIGH | RTL + MSW status classes; prefers API status. |
| Hedge comparison UI | Implemented | PARTIAL | HIGH | Helper + E2E run; no payload assert. |
| Error / loading states | Implemented | PARTIAL | HIGH | ScenarioBuilder API error; dashboard loading; incomplete elsewhere. |
| Deterministic query router | Implemented | GOOD | HIGH | Tool choice; grounded numbers; refuse advisory. |
| LLM tool loop | Provider-agnostic stub | PARTIAL | HIGH | Scripted model tests; no live LLM claimed. |
| No fabricated risk output | Guardrails present | GOOD | HIGH | Unsupported/ambiguous do not call tools. |

## Quant Confidence

**Pricing: 8/10.** Builtin and QuantLib paths have independent closed-form goldens (BS/GK/CIP/STIR/ZC), pinned evaluation dates, and Hypothesis bounds. Remaining gaps are option monotonicity in strike/vol, expiry/zero-vol edges, and honest QL vs Builtin swap residual.

**Greeks: 7/10.** Cash delta/gamma/vega FD properties, bump-and-revalue SensitivityEngine, key-rate isolation, and `portfolio delta ≈ sum(trade deltas)` exist. Bump size is mostly a single choice; theta is explicitly unimplemented.

**VaR: 4/10.** Methodologies exist and are wired. Tests prove determinism, zero-shock → 0, LINEAR vs Δ-Γ vs FULL_REVAL **differ**, and ES ordering. They do **not** prove the quantile, the loss sign, or a known P&amp;L → known VaR.

**Expected Shortfall: 5/10.** Same tail machinery as VaR; contribution **reconciliation** is strong; the **level** of ES is not pinned on a hand-computed tail.

**Stress: 7/10.** Snapshot shocks are exact (e.g. −10% → 90). Zero shock → 0 P&amp;L. Trade/book/desk recon is exact. Combined-factor **P&amp;L** can hide a dropped factor inside `interaction`.

**Reverse Stress: 7/10.** Binary-search convergence, unreachable bound, rates **bp** wire conversion, and determinism are tested. Multi-factor is constrained (documented). Vol reverse may skip the positive assertion if the sample book does not converge.

**Hierarchy/Aggregation: 8/10.** Additive MV/Greeks/stress P&amp;L; VaR/ES recomputed on sub-portfolios (tests do **not** wrongly require child VaRs to sum). Empty book zeros.

**Attribution/P&amp;L Explain: 7/10.** Identical state → 0; 1% equity move → delta 100; residual identity; new-trade flow. Path dependence of sequential bridges is not explored.

## Mutation Resistance

| Hypothetical bug | Would tests detect it? | Evidence |
|---|---|---|
| Flip delta sign | YES | Call unit delta ∈ [0,1]; put ∈ [−1,0]; equity `delta == 250`; FD vs analytic. |
| Flip FX delta sign | YES | Golden `fx_delta ≈ notional × spot`; FD vs analytic on forwards/options. |
| Multiply DV01 by 100 (pricer) | YES | Bond FD vs analytic (`rel=0.25`); IR future `dv01 == -250.0` exact. |
| Multiply DV01 by 100 (VaR P&amp;L only) | NO | Historical tests do not pin VaR vs `DV01 × bp` on a rates-only series. |
| Divide vega by 100 (pricer) | YES | FD vega scaled to 1 vol point; SensitivityEngine `per_vol_point`. |
| Divide vega by 100 (VaR `vol_pct×100` omitted on both NumPy and kernel) | NO | Kernel parity uses the same conversion; VaR tests do not pin `vega × vol_points`. |
| Ignore option quantity | YES | Golden `qty × BS`; intrinsic uses `mv / quantity`; large qty would fail ≥ intrinsic. |
| Ignore futures multiplier | YES | `expected_mv = qty * mult * forward` in QL golden. |
| Reverse FX pair | MAYBE | Pair treated as a string key; no `EURUSD` vs `USDEUR` inversion test. |
| Use 100bp as 100% (0.01 vs 1.00) | YES at snapshot | `50bp → 0.005` decimal in expand tests; rates reverse wire `to_wire_shock`. |
| Use 100bp as 100% in VaR P&amp;L only | NO | No rates-only known-series VaR. |
| Use wrong VaR tail | NO | See QA-001. Ordering still holds on the profit tail. |
| Use wrong ES tail | NO | ES mean of the same wrong tail still ≥ VaR. |
| Remove one trade from hierarchy aggregation | YES | Additive MV/Greeks/stress recon `abs_tol=1e-9`. |
| Ignore one factor in a multi-factor **snapshot** | YES | Combined apply asserts equity, vol, rates, FX marks together. |
| Ignore one factor in multi-factor **P&amp;L attribution** | NO | Residual `interaction` still reconciles (QA-006). |
| Price stress against base market | YES | Custom −50% equity with tiny `max_loss_pct` must `breached is True`; zero-shock vs crash differ. |
| Mutate base snapshot | YES | Frozen mappings; bump returns new object; base marks unchanged. |
| Return base portfolio in what-if | YES | Incremental `after − before`; add increases position count. |
| Swap C++ `dv01` and `fx_delta` columns | YES | Python kernel vs native with distinct nonzero columns; 32×64 matrix. |
| Shift native result by one index | YES | Varying shocks; length + `assert_allclose`. |
| Ignore one P&amp;L explain component (delta on 1% equity) | YES | `drivers[DRIVER_DELTA] == 100` and residual ~0. |
| Ignore gamma in option 5% explain | MAYBE | Residual band `max(1.0, 5% of move)` can absorb a modest gamma miss. |

## Findings

## QA-001 — Historical VaR/ES never pin the loss quantile

Severity: CRITICAL
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
Historical VaR / Expected Shortfall / LINEAR / DELTA_GAMMA / FULL_REVALUATION

Location:
- `backend/app/risk/historical.py:233`
- `backend/app/risk/var.py:103`
- `backend/app/risk/es.py:50`
- `backend/tests/test_risk.py:17`
- `backend/tests/test_var_methodology.py:169`
- `backend/tests/test_m9_risk_properties.py:87`

Evidence:
Loss is defined as `-pnl`, then `np.quantile(losses, 0.95/0.99)` floored at 0. Grep over `backend/tests` finds **no** `np.quantile`, no all-positive P&amp;L case, and no hand-computed 99% VaR on a known series. Typical asserts are `var_99 >= var_95 >= 0` and `expected_shortfall_99 >= var_99`. `test_delta_gamma_default_matches_legacy_seeded_numbers` is named as a numerical regression but only checks ordering.

Failure that could escape:
Implement `var99 = max(0, np.quantile(pnl, 0.99))` (profit tail) or `np.quantile(losses, 0.01)` (wrong percentile). For a two-sided P&amp;L distribution both remain nonnegative and ES of that same tail still ranks above VaR. A book that is always profitable would still report VaR ≥ 0; the documented floor at 0 would hide the sign bug for the all-gain case.

Why current tests would miss it:
Ordering is invariant to which tail is used if ES is computed from the same side. Zero-shock tests stay at 0. Methodology-difference tests only require LINEAR ≠ FULL_REVAL. Component VaR reconciles to **parametric** `z·σ`, which is also tail-side agnostic in the same way.

Recommended test:
Construct a 100-observation P&amp;L (or loss) vector with a unique extreme loss. Assert Historical VaR at 99% equals that observation under the documented interpolation (`numpy` default linear quantile). Repeat with all-positive P&amp;L (expect VaR 0 under loss-floor convention) and a single −1e6 tail event.

Example assertion/invariant:
For losses `[-1, 0, 0, …, 0]` length 100, 99% Historical VaR must be the interpolated 99th percentile of **losses**, not of P&amp;L, and ES must be the mean of observations `>=` that VaR.

Test level:
UNIT

Effort:
S

Suggested roadmap area:
M2 Portfolio Risk / M9 Testing

## QA-002 — LINEAR/DELTA_GAMMA VaR report ignores supplied market snapshots

Severity: HIGH
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
Historical VaR (LINEAR / DELTA_GAMMA) / market snapshot consumption

Location:
- `backend/app/risk/var.py:55`
- `backend/app/risk/historical.py:208`
- `backend/app/services/portfolio_service.py:176`

Evidence:
`VaRAnalytics._position_pnls` comments “Legacy Greek path: position-embedded marks (no shared snapshot)” and calls `pricing.value(p)` with **no** market. `report(..., market=...)` still accepts a snapshot. `HistoricalRiskEngine.calculate` **does** pass `market` into `value_portfolio`. `PortfolioService.var_report` and `summary` can therefore disagree if trade-local marks and the snapshot diverge. No test passes a shocked snapshot into LINEAR `VaRAnalytics.report` and checks Greeks/VaR move.

Failure that could escape:
A caller (risk-change, what-if, future API) supplies yesterday’s snapshot to LINEAR VaR and still gets Greeks from trade `price`/`spot` fields. Displayed VaR does not reflect the intended market.

Why current tests would miss it:
Sample/demo portfolios keep trade marks aligned with `PositionMarketDataProvider.snapshot`. Tests use that default. FULL_REVALUATION tests exercise snapshots; LINEAR does not.

Recommended test:
Equity book with `price=100` and `MarketSnapshot(equity_spots={sym: 110})`. LINEAR VaR cash delta (or a one-point +1% history) must follow the snapshot, not 100.

Example assertion/invariant:
`VaRAnalytics.report(..., methodology=LINEAR, market=shocked).` position Greeks match `pricing.value(pos, shocked)`, not `pricing.value(pos)`.

Test level:
UNIT

Effort:
S

Suggested roadmap area:
M2 Portfolio Risk

## QA-003 — Approximate VaR P&amp;L units are not independently golden

Severity: HIGH
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
LINEAR / DELTA_GAMMA VaR / vega vol points / DV01 bp / native kernel units

Location:
- `backend/app/risk/historical.py:108`
- `backend/app/compute/kernel.py:6`
- `backend/tests/test_historical_scenario_kernel.py:125`
- `backend/tests/test_native_kernel.py:47`

Evidence:
`approximate_pnl_series` converts `vol_pct * 100` into vol points and uses `dv01 * rates_bps`. Native/Python kernel tests prove **parity of the same formula**, including the `×100` in the test’s `Shock(...)` construction. They do not prove that formula against an independent “vega per 1% vol × relative move” business identity on Historical VaR output. No rates-only or vol-only book has an expected `var_99`.

Failure that could escape:
Drop `* 100` in **both** NumPy and kernel (or apply it twice in both). Kernel tests stay green. Sample-book VaR still satisfies ES ≥ VaR. Option-heavy demo VaR could be ~100× too small or too large in the vol term.

Why current tests would miss it:
Parity tests share the convention. Ordering tests are scale-insensitive aside from remaining nonnegative.

Recommended test:
One European option, vol-only history `[0.01]` (relative +1% of vol level), LINEAR VaR/P&amp;L = `vega * 1.0` vol point (or the documented mapping). One bond, rates-only `[1.0]` bp, P&amp;L = `dv01 * 1`.

Example assertion/invariant:
`pnl[i] == vega * (vol_move[i] * 100)` with `rel=1e-12` on a vol-only series.

Test level:
GOLDEN

Effort:
S

Suggested roadmap area:
M2 Portfolio Risk / M6 Native

## QA-004 — CI can go green without executing QuantLib

Severity: HIGH
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
QuantLib production pricing / CI

Location:
- `.github/workflows/ci.yml:36`
- `backend/tests/conftest.py:7`
- `backend/tests/test_quantlib_golden.py:48`
- `backend/tests/test_quantlib_pricing.py:5`
- `backend/tests/test_surface_vol_pricing.py:182`

Evidence:
CI installs `requirements.txt` including QuantLib, but on failure strips QuantLib and continues. Detection sets `RISKFORGE_PRICING_ENGINE` to `builtin` and warns. Adapter tests use `pytest.importorskip` / `skipif`. There is **no** required job that fails if `import QuantLib` fails. E2E forces builtin. Postgres smoke does not need QL. Locally this review ran 659 tests with QL 1.43 and **0 skips**; that does not bind CI.

Failure that could escape:
A QuantLib adapter regression (wrong surface engine, eval-date, fallback to Builtin) never runs on GitHub if the wheel is missing, while README still presents QuantLib as the production adapter.

Why current tests would miss it:
Skips are silent success. Builtin tests still pass.

Recommended test:
CI job with `continue-on-error: false` that `python -c "import QuantLib"` and runs `test_quantlib_*.py` without skip. Optionally fail the workflow if engine output is `builtin`.

Example assertion/invariant:
Job fails unless QuantLib imports and `test_quantlib_golden` collects &gt; 0 tests without skip.

Test level:
CI

Effort:
S

Suggested roadmap area:
M9 Testing / CI / M1 Quant Foundation

## QA-005 — Factor stress contributions can hide a dropped shock in `interaction`

Severity: HIGH
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
Stress contribution decomposition / multi-factor scenarios

Location:
- `backend/tests/test_scenario_attribution.py:189`
- `backend/app/risk/es.py:126` (FULL_REVAL factor residual; same pattern)
- `backend/app/risk/scenario_attribution.py` (factor-isolated + residual)

Evidence:
`test_risk_factor_contributions_reconcile_with_interaction` asserts keys include `interaction` and some equity names, then `sum(contributions) ≈ portfolio_pnl`. If the **combined** revaluation omitted rates (or vol) while isolated legs still ran, residual would absorb the difference and reconciliation would still pass. Isolated-leg tests do not assert a **nonzero rates** contribution on a rates-sensitive book under a combined eq+vol+rates scenario.

Failure that could escape:
Combined crisis P&amp;L ignores `rates_shift_bps` while the factor table still shows a rates line plus a large `interaction`. Users trust recon error ~0.

Why current tests would miss it:
Reconciliation is an accounting identity once residual is defined as `total − sum(isolated)`.

Recommended test:
Rates-only (or DV01-large) book. Combined scenario equity=0, vol=0, rates=+100bp. Assert rates contribution ≈ portfolio P&amp;L and `|interaction|` ≪ |P&amp;L|. Separately, eq+rates combined vs sum of isolated, with a tight residual bound for linear products.

Example assertion/invariant:
For a long ZC bond, `by_risk_factor["USD"]` (or rate key) ≈ `portfolio_pnl` and `|interaction| < 1e-6` when only rates are shocked.

Test level:
UNIT

Effort:
S

Suggested roadmap area:
M3 Stress / M4 Attribution

## QA-006 — User-facing contributors reconcile to parametric VaR, not historical VaR

Severity: HIGH
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
Component VaR / contributors API / dashboard

Location:
- `backend/app/risk/var.py:112`
- `backend/tests/test_component_var.py:1`
- `backend/tests/test_next_phase.py:39`
- `frontend` contributors rendering (API `contribution_pct`)

Evidence:
Comments and tests correctly state Euler allocation of **parametric** `z·σ`. `test_var_report_has_two_methods_and_component_sum` checks `sum(component_var) == pvar`. Nothing asserts that contribution percentages are **not** presented as a decomposition of historical 99% VaR, or that `|sum(component) − historical VaR|` is large on a skewed options book (which would document the methodology). UI/E2E do not distinguish the two numbers.

Failure that could escape:
A change that filled `component_var` from historical ES contributions (or from historical VaR shares) could still sum to 100% of **something** while the dashboard “VaR” tile shows historical quantile. Conversely, historical VaR could be badly wrong while contributors still sum to parametric VaR.

Why current tests would miss it:
They lock the Euler identity to parametric VaR only.

Recommended test:
Options book with skewed P&amp;L. Assert `sum(component_var) == parametric_var` **and** `|sum(component_var) − historical_var| > ε` when distributions are non-normal. API/UI contract test: contributors endpoint schema/docs field `allocates_to: parametric`.

Example assertion/invariant:
On a mixed options book, `abs(sum(component_var) - hist.var) / hist.var > 0.01` while Euler identity holds for `pvar`.

Test level:
UNIT | API

Effort:
S

Suggested roadmap area:
M2 Portfolio Risk / M8 UI

## QA-007 — Core API dashboard tests assert HTTP 200 and list length, not risk meaning

Severity: HIGH
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
API /risk/summary /stress /contributors /limits

Location:
- `backend/tests/test_api.py:12`
- `backend/tests/test_api.py:40`

Evidence:
`test_full_dashboard_flow` checks status 200, `portfolio_id`, `len(stress) >= 5`, contributor count = position count. It does not assert VaR sign, ES ≥ VaR, stress P&amp;L for a known shock, or limit status. Custom stress checks scenario **name** `"Custom"`. Stronger financial asserts exist in engine unit tests, not on the HTTP boundary that the UI uses.

Failure that could escape:
Router wired to a stub that returns zeros/empty Greeks with 200. Or `/risk/summary` dropping `expected_shortfall_99`. Unit engines still pass.

Why current tests would miss it:
Status and cardinality are satisfied by any well-shaped JSON.

Recommended test:
POST `/api/v1/risk/summary` on a one-equity book; assert `market_value == qty*spot`, `var_99 >= 0`, `expected_shortfall_99 >= var_99`. POST custom −10% equity; assert evaluation `pnl == -qty*spot*0.10`.

Example assertion/invariant:
`summary["market_value"] == pytest.approx(250.0)` for 10×25 equity; `evaluations[0]["pnl"] == pytest.approx(-0.10 * MV)`.

Test level:
API

Effort:
S

Suggested roadmap area:
M7 API / M9 Testing

## QA-008 — Scenario percent/bp conversion is not tested at the widget or E2E boundary

Severity: HIGH
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
Scenario Builder / reverse stress UI / hedge default shocks

Location:
- `frontend/src/lib/risk.mjs:322`
- `frontend/src/lib/risk.test.js:42`
- `frontend/src/components/ScenarioBuilder.jsx:44`
- `frontend/src/components/ScenarioBuilder.test.jsx:29`
- `e2e/tests/scenario-builder.spec.ts:4`

Evidence:
`scenarioPayload` correctly maps display `{equity:-20, vol:50, rates:100, fx:-5, limit:10}` → `{equity_shock:-0.2, vol_shock:0.5, rates_shift_bps:100, fx_shock:-0.05, max_loss_pct:0.1}`. `reverseMultiRequestBody` maps `% / 100`. RTL ScenarioBuilder clicks Run and asserts MSW **fixture** text (`Loss $12.0K`); MSW does not inspect the body. E2E fills a name, clicks Run, asserts `/Loss/` — not the request JSON. If `evaluateCustomScenario(portfolio, form)` were called instead of `scenarioPayload(form)`, helper tests still pass.

Failure that could escape:
UI sends `equity_shock: -20` (minus 2000%) or `rates_shift_bps` as `0.01`. Screen still shows a loss. Demo looks “worked.”

Why current tests would miss it:
Conversion is unit-tested in isolation from the click handler and from Playwright network.

Recommended test:
RTL: spy `fetch`/MSW and expect body `equity_shock === -0.2` for default form. E2E: `page.waitForRequest` on `/risk/stress/evaluate/custom` with the same assert. Reverse stress: `target_loss_pct === 0.05` when the input is `5`.

Example assertion/invariant:
Default form equity field `-20` ⇒ JSON `equity_shock == -0.2`, never `-20`.

Test level:
UNIT | E2E

Effort:
S

Suggested roadmap area:
M8 Risk Terminal UI / M9 Testing

## QA-009 — Named seeded VaR “regression” does not lock numerical values

Severity: HIGH
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
DELTA_GAMMA default Historical VaR

Location:
- `backend/tests/test_var_methodology.py:169`

Evidence:
Docstring: “Regression: default path remains the pre-M2.3 Δ-Γ approximation.” Body asserts methodology tag and `var_99 >= var_95 >= 0` and ES ≥ VaR only. Seed `1` and `observations=750` are unused as an expected number.

Failure that could escape:
Any monotonic transform of the loss distribution (scale, tail flip plus floor, quantile 0.95/0.99 swap if both still ordered) keeps the test green while demo VaR changes materially.

Why current tests would miss it:
The test name implies a golden; the asserts do not.

Recommended test:
Store expected `var_95`, `var_99`, `es_99` for `SAMPLE_PORTFOLIO` + seed 1 + 750 obs + builtin, with documented generator. Or hash the P&amp;L series.

Example assertion/invariant:
`r["var_99"] == pytest.approx(<frozen>, rel=1e-12)` for that exact seed/engine.

Test level:
GOLDEN

Effort:
XS

Suggested roadmap area:
M2 Portfolio Risk / M10 Demo

## QA-010 — FULL_REVALUATION VaR is tested for difference, not for shocked PV − base PV

Severity: HIGH
Confidence: MEDIUM
Category: QA
Status: OPEN

Affected capability:
FULL_REVALUATION Historical VaR

Location:
- `backend/app/risk/historical.py:142`
- `backend/tests/test_var_methodology.py:111`
- `backend/tests/test_scenarios.py:150`

Evidence:
`test_full_reval_differs_from_linear_on_options_book` requires `|full.var_99 - linear.var_99| > 1`. Snapshot tests prove shocked spots for a known series (`SPY` 90 then 105). Those are not joined: no test takes a one-equity book, one observation `equity_return=-0.10`, FULL_REVAL `pnl == -0.10 * qty * spot`.

Failure that could escape:
FULL_REVAL uses LINEAR P&amp;L internally but a small nonlinear tweak keeps VaR different from LINEAR on the options book. Or it reprices the **base** snapshot every step (P&amp;L ~0) except when tests only check methodology labels on zero-shock series.

Why current tests would miss it:
“Differs from linear” is a weak inequality. Zero-shock FULL_REVAL is 0 for both a correct reval and a constant-zero bug after the zero series.

Recommended test:
Single equity, `ArrayHistoricalDataset` with one row −10% equity, others 0. `full_revaluation_pnl_series[i] == qty*spot*(-0.10)`.

Example assertion/invariant:
`pnl == pricing.value(pos, shocked).market_value - pricing.value(pos, base).market_value` elementwise.

Test level:
GOLDEN

Effort:
S

Suggested roadmap area:
M2 Portfolio Risk

## QA-011 — Missing vanilla option monotonicity properties (strike and vol)

Severity: MEDIUM
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
Equity / FX option pricing

Location:
- `backend/tests/test_quant_properties.py` (delta bounds, intrinsic, FD; no strike/vol monotone)
- `backend/tests/test_pricing.py:22`

Evidence:
Hypothesis covers unit delta, discounted intrinsic, bond yield, payer swap, portfolio PV, zero shock, FD Greeks. There is no `call(K2) ≤ call(K1)` for `K2>K1`, nor “higher vol ⇒ higher vanilla value” (except vega sign on one example).

Failure that could escape:
Strike and spot swapped in the BS formula could still produce delta in [0,1] near ATM and price ≥ intrinsic for some draws.

Why current tests would miss it:
Intrinsic and delta bounds are necessary but not sufficient for the call being decreasing in strike.

Recommended test:
Two Hypothesis (or three fixed) strikes; ATM vs +10% vol for a long call/put.

Example assertion/invariant:
`value(call, K=110) <= value(call, K=100)` at equal other inputs; `value(vol=0.30) >= value(vol=0.20)`.

Test level:
PROPERTY

Effort:
XS

Suggested roadmap area:
M1 Quant Foundation

## QA-012 — No test that two QuantLib engines isolate evaluation date

Severity: MEDIUM
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
QuantLib global `Settings.evaluationDate` / concurrency

Location:
- `backend/app/pricing/quantlib.py:59`
- `docs/adr/007-quantlib-concurrency.md`
- `backend/tests/test_quantlib_golden.py:186`

Evidence:
Adapter uses `RLock` and restores previous eval date. Tests pin a single engine date (including weekend/leap). No test constructs two engines with different dates and interleaves `value()` calls, or runs threaded FULL_REVAL. ADR 007 describes the risk; tests do not exercise the restore path under contention.

Failure that could escape:
A future call site that sets `ql.Settings` without `_session`, or a lock regression, could price T+wrong calendar while goldens still pass sequentially.

Why current tests would miss it:
Each test uses one engine, one date, one thread.

Recommended test:
Engine A date 2026-09-01, engine B 2024-02-29; alternate `value()` on the same ATM option; each matches its analytic with that date’s year fraction.

Example assertion/invariant:
Interleaved `engine_a.value(opt) ≈ bs(T_a)` and `engine_b.value(opt) ≈ bs(T_b)`.

Test level:
UNIT

Effort:
S

Suggested roadmap area:
M1 Quant Foundation / ADR 007

## QA-013 — QuantLib stress smoke only asserts inequality

Severity: MEDIUM
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
QuantLib `shocked_value` / option stress

Location:
- `backend/tests/test_quantlib_pricing.py:85`

Evidence:
`test_stress_revalues_option` asserts `shocked_value != value`. Any nonzero bug (wrong shock, double count, currency mix-up) still passes.

Failure that could escape:
Shock applied with inverted vol sign still ≠ base for a put.

Why current tests would miss it:
Inequality is the weakest possible numeric check.

Recommended test:
Put, equity −10%, compare to Builtin `shocked_value` within existing option rel band, or to `value(put, shock_snapshot(...))`.

Example assertion/invariant:
`ql.shocked_value(put, scenario) == pytest.approx(ql.value(put, shocked_snap).market_value, rel=2e-3)`.

Test level:
UNIT

Effort:
XS

Suggested roadmap area:
M1 / M3

## QA-014 — E2E covers panels, not one defensible user journey or request units

Severity: MEDIUM
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
E2E / Scenario Builder / hedge / VaR

Location:
- `e2e/tests/dashboard.spec.ts`
- `e2e/tests/scenario-builder.spec.ts`
- `e2e/tests/m8-panels.spec.ts`
- `e2e/playwright.config.js` (`RISKFORGE_PRICING_ENGINE: builtin`)

Evidence:
12 Playwright tests passed locally (Chrome channel). They assert headings, tables nonempty, “Loss”, “Converged”, COMPLETED/FAILED. No test: load portfolio → read VaR → run custom scenario → inspect contributors → apply hedge → rerun → assert VaR changed. No test asserts request bodies. E2E never uses QuantLib.

Failure that could escape:
Broken hedge construction that still returns 200 and a table. Unit conversion bug (QA-008). QuantLib-only UI issue.

Why current tests would miss it:
Success is “something rendered.”

Recommended test:
One Playwright flow with network assertions on `/risk/var`, `/risk/stress/evaluate/custom` (body units), `/risk/stress/compare`, and `hedged_var_99 !== base_var_99` from API JSON (still no client-side math).

Example assertion/invariant:
After hedge compare, `hedged_var_99` from the JSON differs from `base_var_99` when SPY equity is flattened.

Test level:
E2E

Effort:
M

Suggested roadmap area:
M9 Testing / M8 UI

## QA-015 — Durable Postgres path is CI smoke, not pytest

Severity: MEDIUM
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
Persistence / worker SKIP LOCKED / Alembic

Location:
- `.github/workflows/ci.yml:80`
- `backend/tests/test_durable_worker.py`
- `backend/tests/test_persistence.py`
- `scripts/smoke_postgres.sh`

Evidence:
Unit tests use SQLite or in-memory repos. Worker claim on SQLite is FIFO without `SKIP LOCKED`. CI `postgres-persistence-smoke` is a separate job. No pytest mark `postgres` in the 659.

Failure that could escape:
`FOR UPDATE SKIP LOCKED` SQL dialect bug, migration drift, or JSON payload serialization on Postgres-only types. SQLite tests stay green.

Why current tests would miss it:
Different SQL dialect and locking.

Recommended test:
Optional pytest job using the compose DSN: two workers cannot complete the same `QUEUED` row; alembic head round-trip.

Example assertion/invariant:
Two concurrent `claim_queued` return distinct run ids; row never `COMPLETED` twice.

Test level:
INTEGRATION | CI

Effort:
M

Suggested roadmap area:
M5 Persistence / M9 CI

## QA-016 — Option expiry, zero vol, and near-zero T are weakly covered

Severity: MEDIUM
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
European equity/FX options / QuantLib T clamp

Location:
- `backend/app/pricing/quantlib.py:77`
- `backend/tests/test_quant_properties.py:68` (`maturity_s` min 0.05)
- `backend/tests/test_quantlib_golden.py` (module notes short T live in pricing tests with wider bands)

Evidence:
Property strategies exclude very short T and low vol. Clamp-to-1-calendar-day is documented. No test for expired (`T=0` domain), `vol=0` intrinsic, or strike ≤ 0 rejection.

Failure that could escape:
Zero vol returns NaN from `log`/`sqrt` and leaks into VaR. Expired options still show time value.

Why current tests would miss it:
Happy-path ATM 0.25–1Y examples.

Recommended test:
`vol=0` price = discounted intrinsic; `T→0` policy documented and asserted; invalid strike rejected by the domain model.

Example assertion/invariant:
`vol=0` call value `== quantity * exp(-rT)*max(F-K,0)` (or the documented clamp).

Test level:
UNIT

Effort:
S

Suggested roadmap area:
M1 Quant Foundation

## QA-017 — FX pair reversal and malformed pairs are untested

Severity: MEDIUM
Confidence: MEDIUM
Category: QA
Status: OPEN

Affected capability:
FX forward / FX option / FX delta

Location:
- `backend/tests/test_quantlib_golden.py:457`
- `backend/app/pricing/builtin.py` (pair as dict key)

Evidence:
Goldens use `EURUSD` only. No `USDEUR`, no missing `fx_spots` fallback behavior test beyond generic snapshot get, no inverted quote.

Failure that could escape:
Domestic/foreign rates swapped for a reversed pair; FX delta sign still “looks” large.

Why current tests would miss it:
All fixtures share one pair convention.

Recommended test:
Missing pair → documented fallback; reject unknown pair on FX trades if that is the contract.

Example assertion/invariant:
Pricing `USDEUR` is either rejected or equal to the reciprocal convention documented in methodology.

Test level:
UNIT

Effort:
S

Suggested roadmap area:
M1 Quant Foundation

## QA-018 — Sensitivity bump-size stability is not tested

Severity: MEDIUM
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
Bump-and-revalue Greeks / DV01

Location:
- `backend/tests/test_sensitivities.py:32`
- `backend/tests/test_quant_properties.py:327`

Evidence:
FD uses one `spot_bump` / `vol_h=1e-4`. No comparison of 1bp vs 10bp DV01 or 0.1% vs 1% spot bump besides single-point agreement with analytic.

Failure that could escape:
One-sided difference with a huge bump passes 25% bond DV01 band but is unstable on options gamma.

Why current tests would miss it:
Single bump size.

Recommended test:
Option gamma/vega for two bump sizes within a relative band; DV01 1bp vs 0.1bp on a bond.

Example assertion/invariant:
`|dv01(1bp) - dv01(0.1bp)| / |dv01(1bp)| < 0.05` on a plain ZC.

Test level:
UNIT

Effort:
S

Suggested roadmap area:
M1 Sensitivities

## QA-019 — Documentation still describes older, smaller suites

Severity: MEDIUM
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
Docs vs test reality / recruiter claims

Location:
- `BUILD_NOTES.md:5` (“32 passed, 1 skipped”)
- `ROADMAP.md:29` (160 passed) and `ROADMAP.md:72` (519 passed)
- `README.md:181` (commands are current; QL skip policy described)

Evidence:
This review: **659** backend passed, **0 skipped**, frontend **74**, E2E **12**. BUILD_NOTES still describes a sandbox with QuantLib skipped and npm build blocked. ROADMAP acceptance tables are stale. README is closer to reality (importorskip only when wheel absent).

Failure that could escape:
Interviewers/agents treat BUILD_NOTES as current evidence that QL is untested, or treat 519 as the suite size and miss new gaps.

Why current tests would miss it:
Docs are not tested except `test_m39_methodology_docs.py` (2 tests).

Recommended test:
Do not add a brittle test count. Refresh BUILD_NOTES/ROADMAP verification tables in a docs change (out of scope here).

Example assertion/invariant:
Published verification numbers match a dated CI run or are clearly historical.

Test level:
CI

Effort:
XS

Suggested roadmap area:
M12 Documentation

## QA-020 — mypy/Ruff success is staged and can create false typing confidence

Severity: MEDIUM
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
Static analysis CI

Location:
- `backend/pyproject.toml:26`
- `backend/pyproject.toml:75`
- `.github/workflows/ci.yml:159`

Evidence:
Ruff ignores include E501, several B/UP/SIM/RUF codes. mypy disables `arg-type`, `assignment`, `var-annotated`, `no-redef`, `misc`. `check_untyped_defs = false`. CI job is green; comments say this is debt.

Failure that could escape:
Wrong optional market argument types, swapped float/int conventions at API boundaries.

Why current tests would miss it:
The tools are configured not to see those errors.

Recommended test:
Do not treat mypy green as “fully typed.” Track remaining `disable_error_code` as a quality backlog (no code change in this review).

Example assertion/invariant:
A future tightening PR should enable `arg-type` on `app/risk/var.py` first.

Test level:
CI

Effort:
L

Suggested roadmap area:
M9 Testing / CI

## QA-021 — API does not test NaN/Infinity or oversized payloads

Severity: LOW
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
API validation

Location:
- `backend/tests/test_api_error_model.py`
- `backend/tests/test_api_typed_models.py`

Evidence:
Error shape `{code,message,details}` and 422 paths exist. No JSON `NaN`, `Infinity`, or huge portfolio tests.

Failure that could escape:
NaN in `quantity` becomes a 500 or a silent NaN VaR in JSON.

Why current tests would miss it:
Malformed-but-finite 422 cases only.

Recommended test:
POST summary with `"quantity": "NaN"` or `null`; expect 422 error body.

Example assertion/invariant:
Status 422, `code` validation, no 500.

Test level:
API

Effort:
XS

Suggested roadmap area:
M7 API

## QA-022 — Zero and negative limit bounds are implemented but untested

Severity: LOW
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
Limits

Location:
- `backend/app/risk/limits.py:82`
- `backend/tests/test_limits.py:28`

Evidence:
`limit <= 0` → BREACH if `value > 0` else OK. Tests cover 80/100/100.01 utilization on **positive** limits. No `limit=0`, negative limit, or missing metric.

Failure that could escape:
Zero limit mis-classified as WARNING via division; code currently special-cases `limit <= 0`, so a **regression** that deletes that branch would be untested.

Why current tests would miss it:
Happy positive limits only.

Recommended test:
`classify_limit_status(1.0, 0.0, 80) == "BREACH"`; `classify_limit_status(0.0, 0.0, 80) == "OK"`.

Example assertion/invariant:
As above.

Test level:
UNIT

Effort:
XS

Suggested roadmap area:
M4 Limits

## QA-023 — Duplicate trade IDs and invalid instrument types are untested

Severity: LOW
Confidence: MEDIUM
Category: QA
Status: OPEN

Affected capability:
Portfolio domain / hierarchy / VaR maps keyed by `p.id`

Location:
- `backend/app/risk/var.py:54` (`out[p.id]`)
- `backend/tests/test_hierarchy.py`

Evidence:
No duplicate-id fixture. Dict-keyed P&amp;L would silently drop a trade.

Failure that could escape:
Import of a book with duplicate IDs understates VaR and hierarchy.

Why current tests would miss it:
All fixtures have unique ids.

Recommended test:
Constructing `Portfolio` with two `id="eq-1"` either errors or risk engines detect collision.

Example assertion/invariant:
`ValueError` or `len(contributions) == 2` with distinct keys — pick the documented contract and test it.

Test level:
UNIT

Effort:
XS

Suggested roadmap area:
M0 Domain

## QA-024 — E2E and demo path never exercise QuantLib

Severity: LOW
Confidence: HIGH
Category: QA
Status: OPEN

Affected capability:
E2E / production adapter

Location:
- `e2e/playwright.config.js` env `RISKFORGE_PRICING_ENGINE: builtin`
- README demo smoke uses packaged artifact

Evidence:
Playwright always builtin. Nightly QuantLib E2E does not exist.

Failure that could escape:
QL-only pricing difference that still 200s on builtin demo numbers.

Why current tests would miss it:
Different engine in UI vs intended production.

Recommended test:
Optional nightly job with QL engine and a **range** check against `data/demo_risk_artifact.json` (not bit-identical NPVs for swaps).

Example assertion/invariant:
Demo 99% VaR within documented artifact bands under QL.

Test level:
E2E | CI

Effort:
M

Suggested roadmap area:
M9 / M13 Demo

## QA-025 — Native ctypes ABI does not test caller length mismatch

Severity: LOW
Confidence: MEDIUM
Category: QA
Status: OPEN

Affected capability:
Native scenario kernel FFI

Location:
- `backend/app/compute/kernel.py:107`
- `backend/native/src/risk_kernel_capi.cpp:9`

Evidence:
C API trusts `n_exposures` / `n_shocks`. Python always derives them from list lengths. Tests never pass a wrong `n`. An index bug **inside** matching lengths **is** covered (QA mutation table YES).

Failure that could escape:
A future wrapper that passes `len(shocks)-1` would omit the last scenario; current tests would not represent that wrapper.

Why current tests would miss it:
Happy-path lengths only.

Recommended test:
If the C API cannot validate, document undefined behavior. Optionally a death test is out of scope for ctypes.

Example assertion/invariant:
Python wrapper rejects empty vs mismatched flattened buffers if a flattened API is exposed.

Test level:
NATIVE

Effort:
S

Suggested roadmap area:
M6 C++ Performance

## Edge Case Gaps

Covered well: empty portfolio (zero risk), empty/zero shocks, frozen snapshots, native empty/NaN, limit 80/100/100.01, reverse unreachable bound, worker QUEUED→COMPLETED, cache miss on bump.

Material gaps (not duplicated as extra findings): huge portfolios; duplicate IDs (QA-023); zero/negative notional if invalid; expired options (QA-016); spot/strike zero; missing curve node beyond key-rate fallback tests; malformed FX pair (QA-017); conflicting broad vs symbol shocks (symbol-specific NVDA test exists in `test_next_phase.py`); VaR one-observation / identical observations (zero-shock is the identical case); API NaN (QA-021); oversized payload.

## Golden Test Assessment

**What exists:** Strong QuantLib goldens with **pinned `evaluation_date`**, independent `NormalDist` BS/GK, CIP futures/forwards including **multiplier**, algebraic IR future, continuous ZC vs QL, ATM/ITM/OTM option grid, FX option notional×GK. Caps/floors/swaptions have **independent Black-76** references in `test_ir_options_pricing.py`. Builtin vs QL rel bands are documented (`2e-3` options, `1e-12` CIP).

**What is missing:** No frozen Historical VaR/ES number for a named book+seed (QA-009). No 1-observation FULL_REVAL cash equity P&amp;L golden (QA-010). No SPX-style published vendor quote; goldens are model-consistent, not street-sheet. Swap QL vs Builtin is sign/monotonicity, not NPV golden.

**QuantLib vs reference:** Meaningful where algebra is shared (equity, future, FX, ZC, IR future). Swap residual is honestly documented. Surface tests assert QL must not silently use `BlackConstantVol` when a grid is attached.

## Property Testing Assessment

Hypothesis is used in `test_quant_properties.py` and `test_m9_risk_properties.py` (`max_examples` 60/40). High-value properties present: long call/put unit delta, price ≥ discounted intrinsic, bond yield, payer swap, portfolio PV sum, zero shock, ES ordering, stress recon, component Euler, long-equity more-negative shock.

Highest-value missing properties: call decreasing in strike; vanilla increasing in vol; snapshot shock does not mutate base (already **example** tests, property optional); LINEAR VaR exact Greek×shock (better as golden); all-positive P&amp;L VaR=0.

Do not add property tests that only restate `ES >= VaR`.

## API Testing Assessment

**Medium-high** for platform (v1 compatibility, deprecation headers, OpenAPI examples, typed models, error envelope, risk-run lifecycle, what-if validation). **Weak** for financial meaning on the dashboard endpoints (QA-007). Dual-mount is tested. No NaN/versioning-break tests beyond sunset headers.

## Frontend Testing Assessment

**Good** on pure display helpers (`money`, hierarchy walks, `scenarioPayload`, reverse-multi `%→fraction`, limit status CSS, hedge flatten does not mutate). **Partial** RTL: ScenarioBuilder, Limits, ReverseStressMulti, AppNav, MetricCard. Analytics/hierarchy/attribution/hedge are mostly E2E smoke. Conversion bugs at the **click** boundary are the main residual risk (QA-008).

## Native C++ Testing Assessment

**Strong** for the scoped kernel: exact ABI formula, serial vs parallel, ctypes vs Python, NumPy historical path vs kernel, empty/zero/NaN, 32×64 grid. Column swap and output index shift would fail. FULL_REVALUATION correctly refused. Performance SLA lives in `benchmarks/`, not in unit wall-clock asserts. FFI does not validate lying lengths (QA-025).

## E2E Assessment

12 tests passed on Chrome channel (builtin API + Vite). Coverage: dashboard metrics visible, scenario builder loss, reverse stress (single + multi validation/status), risk query routing, risk-run terminal status, ES table, VaR compare labels, hedge compare, collage navigation.

Missing critical **single** flow (load → VaR → stress → contributors → hedge → rerun). No numeric or request-body asserts. QuantLib unused. First Chromium-bundle attempt failed on macOS 13 — local docs are right; CI Ubuntu path is the one that proves bundled Chromium.

## CI Assessment

Jobs match README reasonably: backend pytest (QL preferred, **optional**), native compile on Ubuntu, Postgres smoke, frontend test+build, Ruff/mypy/ESLint, Playwright with `CI=true` Chromium.

Gaps: QuantLib not a hard gate (QA-004); pytest does not run Postgres (QA-015); E2E builtin-only (QA-024); mypy/Ruff staged (QA-020); no nightly large-history/FULL_REVAL job.

## Test Pyramid Assessment

- **Unit / engine:** Dominant and often high quality (snapshots, hierarchy, attribution, limits, IR options, goldens).
- **Property:** Present and well targeted for pricing; VaR properties are mostly ordering.
- **Golden:** Excellent for **pricing**; thin for **VaR/ES**.
- **Integration/API:** Broad surface, mixed semantic depth.
- **Native parity:** Appropriate middle layer.
- **E2E:** Sensibly small (12), but too shallow on contracts.
- **Performance:** Separated under `benchmarks/` — correct.

The pyramid is not “E2E-heavy.” It is “unit-heavy with a VaR hole at the golden layer.”

## Recommended Test Execution Tiers

### PR-FAST

- `cd backend && PYTHONPATH=. RISKFORGE_PRICING_ENGINE=builtin pytest -q -m "not slow"` (if a slow mark is added later) **or** current full pytest minus native compile if split.
- `tests/test_quant_properties.py`, `test_pricing.py`, `test_var_methodology.py`, `test_market_snapshot.py`, `test_hierarchy.py`, `test_attribution.py`, `test_limits.py` — until marks exist, keep **full 659** given ~36s locally.
- `cd frontend && npm test && npm run lint`

### PR-FULL

- Same pytest with **required** `import QuantLib` (no skip).
- Native `g++` kernel_test + shared lib (already in CI backend job).
- `npm run build`
- Playwright Chromium (Ubuntu) / Chrome channel (macOS 13).
- Ruff + mypy (current staged config).

### NIGHTLY / PERFORMANCE

- Postgres pytest or extended smoke (two workers, SKIP LOCKED).
- QuantLib E2E vs demo artifact **ranges**.
- `benchmarks/check_m6_sla.py` on a labeled runner (not PR gate unless hardware is stable).
- Larger FULL_REVALUATION observation counts; optional kernel 10k×1k **parity** sample, not wall-clock in pytest.

## Positive QA Decisions

- Immutable `MarketSnapshot` with tests that mutation raises and base marks stay put.
- Honest crisis-library labeling (`HISTORICAL_APPROXIMATION`, not replay).
- Packaged demo CSV tested as deterministic synthetic replay, not a vendor feed.
- Explicit numerical tolerances and convention comments at the top of many test modules.
- Hierarchy tests **recompute** VaR/ES per node and add only MV/Greeks/stress P&amp;L.
- Attribution identical-state zero and `explained + residual = actual`.
- Limit classifier tests include 80% inclusive WARNING and `value == limit` not BREACH.
- Native kernel tests use **distinct** delta/gamma/vega/dv01/fx_delta so column swaps fail.
- `conftest.py` resets curve/scenario LRU caches every test.
- QuantLib goldens pin evaluation dates (including weekend/leap day).
- AI query tests prove numbers come from tool payloads (`444` present, fixture `333` absent) and advisory prompts do not call the engine.
- Pricing cache tests prove hit/miss and market-bump invalidation with counting inner engine.
- Incremental/what-if tests prove the base portfolio is not mutated.
- Reverse-stress rates wire: `0.1` magnitude → 100bp display, decimal bump 0.01.
- Frontend `scenarioPayload` / `reverseMultiRequestBody` unit conversions are correct where tested.
- Performance benches are not mixed into correctness pytest as wall-clock asserts.
- Worker tests cover QUEUED until poll, COMPLETED persistence, external-worker flag.

## Final Assessment

1. **Can we trust current pricing results?** **Mostly yes** for the scoped instrument set on Builtin and on QuantLib **when the wheel is actually tested**. Goldens and properties are the strongest part of the suite. Do not trust expiry/zero-vol/unlisted FX pairs or QL-vs-Builtin swap NPV equality.

2. **Can we trust current Greeks?** **Yes for sign and order of magnitude** on listed measures (delta/gamma/vega/DV01/key-rate/FX delta) via FD and bump-and-revalue. Do not treat a single bump size as a stability proof. Theta is not implemented.

3. **Can we trust current VaR / ES?** **Not as a defensible quantile.** We can trust determinism, zero-shock → 0, ES ≥ VaR ordering, and Euler **parametric** allocation. We cannot trust that the **loss tail**, percentile, or vol/bp scaling of approximate P&amp;L is correct (QA-001, QA-003, QA-006, QA-009).

4. **Can we trust current stress results?** **Yes for snapshot math and zero-shock P&amp;L**, and for trade-level recon. Treat factor-level recon as accounting including residual, not as proof every shock entered the combined PV (QA-005).

5. **Can we trust attribution/reconciliation?** **Yes for P&amp;L explain identities** on tested drivers (especially cash equity delta). Residual bands on options Taylor are looser. Risk-change attribution is thinner than P&amp;L explain.

6. **Top 3 test gaps to fix before adding more features:**
   - Exact Historical VaR/ES on a known P&amp;L vector (wrong-tail).
   - Independent LINEAR P&amp;L goldens for vol-points and DV01×bp (and FULL_REVAL `PV_shock − PV_base`).
   - Hard CI QuantLib gate plus Scenario Builder **request-body** conversion tests.

7. **Where passing tests create false confidence:** 659 green tests; `test_delta_gamma_default_matches_legacy_seeded_numbers`; component VaR summing to 100% (parametric, not historical); stress factor recon including `interaction`; mypy/Ruff green under disabled codes; E2E “Loss” without units; CI backend job that can drop QuantLib and still pass; BUILD_NOTES/ROADMAP suite counts that no longer match this tree.
