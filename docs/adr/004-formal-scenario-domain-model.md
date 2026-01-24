# ADR 004: Formal Scenario domain model with typed factor shocks

- Status: Accepted (M3.1)
- Date: 2026-09-02
- Owners: Stress & Scenario Engineer; Lead Architect (contract)

## Context

MVP stress uses ``StressScenario`` with scalar and per-name dict shock fields
(`equity_shock`, `equity_shocks`, …). Historical VaR (M2.2) introduced
``MarketScenario`` / ``FactorChange`` over typed ``RiskFactor`` instances, but
threat evaluation, custom stress APIs, and reverse stress still speak the legacy
flat shape.

Milestone 3 needs a formal scenario definition: identity, category, typed
shocks, governance threshold, severity, and metadata — without breaking
existing stress/what-if endpoints.

## Decision

1. Introduce ``Scenario`` / ``FactorShock`` / ``ScenarioCategory`` /
   ``ScenarioThreshold`` / ``ScenarioSeverity`` in
   ``backend/app/risk/scenario_model.py`` as the internal formal model.
2. Shocks reference typed ``RiskFactor`` values from ``risk/factor_types.py`` and
   apply only via ``MarketSnapshot.apply`` / ``bump``.
3. Keep ``StressScenario`` as the stable wire/API DTO for current endpoints.
   Bidirectional adapters (`scenario_from_stress`, `scenario_to_stress`, and
   MarketScenario bridges) preserve numerical equivalence with
   ``shock_snapshot``.
4. Severity band boundaries stay aligned with ``StressEngine`` threat levels
   (3% / 8% / 15% of |NAV|). Historical-style presets default to
   ``HISTORICAL_APPROXIMATION``; observation-derived scenarios map to
   ``HISTORICAL_REPLAY``.

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| Replace ``StressScenario`` in-place with typed shocks | Breaking API/OpenAPI change across Backend, Frontend, what-if |
| Duplicate shock logic inside instrument classes | Violates scenario charter and ADR 002 |
| Only extend ``MarketScenario`` | Missing threshold / severity / category governance fields |

## Consequences

- M3.2+ multi-factor engine and crisis library should build on ``Scenario``.
- **M3.8 (2026-09-02):** formal ``ScenarioWire`` / ``FactorShockWire`` exposed on
  versioned routes ``GET /api/v1/risk/stress/scenarios/formal``,
  ``POST /api/v1/risk/stress/formal/custom``,
  ``POST /api/v1/risk/stress/formal/evaluate/custom`` (see ``app.api.scenario_wire``).
  Adapters project to ``StressScenario`` for ``StressEngine``; legacy endpoints
  unchanged. Hedge-compare / what-if remain on ``StressScenario`` until a follow-on.
- Declared ``severity`` on a definition is optional metadata; realized severity
  still comes from ``classify_severity(loss_pct_nav)`` after revaluation.
