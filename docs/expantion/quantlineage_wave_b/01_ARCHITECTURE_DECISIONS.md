# Wave B Architecture Decisions

1. Backend owns return, volatility, drawdown, Sharpe, beta, tracking error, VaR/ES and attribution math.
2. Historical analytics always reference frozen portfolio/data identities and explicit date range/config.
3. Prefer one canonical historical analytics result powering summary metrics and time-series charts.
4. Benchmark analysis is relative analytics, not allocation advice.
5. Risk visuals consume existing backend risk artifacts.
6. Risk-change waterfall consumes RiskChangeReport; frontend does not reconstruct attribution.
7. Every chart exposes units and sign convention.
8. Charting library stays presentation-only.
9. Annualization conventions must be explicit and tested.
10. Range changes create new analysis requests; they do not mutate frozen data.
11. Synthetic and Wave A public data share one backend analytics path.
12. No optimizer/retirement scope in Wave B.
