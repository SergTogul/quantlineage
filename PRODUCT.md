# Product

## Platform

web

## Users

Primary: a desk / portfolio risk user at a multi-asset book. They open the terminal to scan VaR, limits, and what moved, then drill into a breach or a top contributor.

Other audiences (demo walkthroughs, CRO overnight review) exist in the repo but are not the dashboard’s primary job.

## Product Purpose

QuantLineage is an institutional-style multi-asset portfolio and derivatives risk-management platform. Mature pricing libraries such as QuantLib price instruments. QuantLineage owns portfolio aggregation, market snapshots, risk factors, VaR/Expected Shortfall, stress testing, reverse stress, P&L/risk attribution, limits, hierarchy, scenario computation, and the user workflow.

The dashboard is a command center: one screen that answers “is the book OK, and if not, where?” then routes into existing VaR, stress, and limits workflows.

Success: within ~30 seconds the user knows book status, the worst threat, limit condition, and the next drill target — from API payloads only.

## Positioning

The pricing library prices. QuantLineage manages portfolio risk. The model orchestrates deterministic tools; it never calculates financial risk itself. The UI must not duplicate pricing or risk formulas, invent numbers, or hide provenance.

## Operating Context

- React/Vite risk terminal (`frontend/`) talking to FastAPI under `/api/v1`.
- Hash-routed sections: Overview, Portfolio, Risk Factors, VaR & ES, Stress, Scenario Builder, P&L Explain, Limits, Risk Runs.
- Demo books (`equity-vol`, `rates-macro`, `global-macro`) and packaged synthetic history; no live market-data vendors.
- Overnight / start-of-day scan on a desktop monitor; mobile is secondary collapse, not the design target.
- Help copy on blocks explains methodology; numbers come from loaded dashboard batch and follow-on POSTs.

## Capabilities and Constraints

Confirmed in the current terminal (keep):

- Overview KPIs from API summary + threat report
- Portfolio hierarchy and positions
- Risk-factor exposures and heatmaps
- VaR/ES analytics, contributors, ES contributions, methodology compare, risk-change attribution
- Stress P&L, threat scenarios, reverse stress (single and multi-factor)
- Scenario builder, hedge compare, deterministic risk query
- P&L explain / attribution
- Limits utilization, status, drill-down
- Async risk-run start and poll

Hard constraints (user-confirmed):

- UI never invents or computes risk numbers — display API results only, with provenance.
- Keep the current capability set; redesign may restructure information architecture and navigation, not drop those workflows.

Undecided:

- Whether a standing build-path default (comp-first vs code-first) should be stored for the project.

## Brand Commitments

- Product name: **QuantLineage**. Header/subtitle: **AI-Powered Multi-Asset Risk & Attribution Platform**. Nav wordmark is QUANTLINEAGE.
- Voice: precise, institutional, methodology-honest. No hype, gamification, or invented commercial claims.
- Standing visual preference (user-locked 2026-09-11): the category-standard dark KPI risk terminal, played straight. Quality bar is **Bloomberg Terminal** craft (density, black ground, amber selection, tabular figures) without cloning Bloomberg chrome or wordmarks. Not a paper circular, dispatch board, or Metro tile world.
- No separate logo or brand kit is in the repo.

## Evidence on Hand

- Demo screenshots: `docs/demo/quantlineage_demo_01_overview.png` and sibling captures.
- Deterministic artifact: `data/demo_risk_artifact.json` (builtin engine). Demo ranges in `docs/demo/final_demo.md` (e.g. default `global-macro` MV ~$2.63M, 99% VaR ~$44.1K, ES ~$51.9K).
- Incumbent Overview: five equal-weight KPI cards, eight “terminal map” jump tiles, hierarchy and factor heatmap teasers. Dark navy shell, Inter, mint accent.
- No customer testimonials, live vendor feeds, or production SLAs to display. Future work must not fabricate those.

## Product Principles

1. Display, don’t calculate — every figure is an API result with a visible source.
2. Status before scenery — the first viewport answers whether the book is OK, then where to go.
3. Drill, don’t duplicate — overview concentrates judgment and routes into existing specialist surfaces.
4. Honest methodology — labels name confidence, engine, snapshot, and known limitations rather than implying a certified optimum.
5. One capability set — VaR, stress, reverse stress, limits, hierarchy, attribution, runs, and query remain reachable.
