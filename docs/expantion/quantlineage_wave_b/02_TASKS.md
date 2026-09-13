# Wave B Tasks

## B1 Historical Analytics Backend
Build deterministic backend analytics:
- cumulative/wealth series
- annualized return
- annualized volatility
- max drawdown + drawdown series
- rolling volatility
- Sharpe
- historical VaR/ES
- best/worst periods

Define request/result with portfolio version, dataset id/version, range, frequency, methodology and annualization convention.

Tests: constant returns, zero vol, known drawdown, known Sharpe, VaR/ES tail, short windows, missing dates.

## B2 Benchmark / Relative Risk
Add canonical benchmark identity from Wave A and deterministic alignment.

Metrics:
- benchmark cumulative return
- excess return
- correlation
- beta
- tracking error
- relative drawdown
- benchmark VaR/ES

Tests: identical series => beta~1, TE=0; uncorrelated series; shifted dates; insufficient overlap.

## B3 Institutional Risk Visuals
Add:
- factor contribution bars
- concentration heatmap/table
- stress comparison
- KR-DV01 tenor curve
- VaR/ES trend if stored run series support it

Parallel DV01 and KR-DV01 must remain separately labeled.

## B4 Flagship Risk-Change Waterfall
Render:
T0 risk → portfolio/trade change → market/factor changes → residual/interactions → T1 risk.

Drill: Firm → Desk → Book → Trade → Factor.
Show changed portfolio version, snapshot, dataset, methodology and config.
Residual is always visible.

## B5 Historical Analytics UI
One coherent page:
- identity / data provenance
- summary metrics
- cumulative return
- drawdown
- rolling vol
- benchmark comparison
- VaR/ES
- link to contributors / risk-change

Range controls call backend. No financial recalculation in browser.

## B6 Demo
5–8 minute flow:
data → historical analytics → SPY comparison → drawdown/risk → contributors → KR-DV01 → T0/T1 waterfall → provenance.

Create `docs/historical_analytics_demo.md`.

## B7 Hostile Review
Attack:
- percent/fraction
- CAGR/vol annualization
- drawdown sign
- Sharpe zero-vol
- beta denominator
- tracking-error annualization
- P&L vs loss
- bp vs currency
- benchmark date mismatch
- stale async UI response
- hidden residual
- frontend financial recomputation

Create `reviews/wave-b-analytics-hostile-review.md`.
