# ADR 003: Typed risk-factor taxonomy

- Status: Accepted (M1.6 complete in code; API still string-keyed)
- Date: 2026-09-02
- Owners: Lead Architect; Market Data & Curves Engineer; Portfolio Risk Engineer (consumer)

## Context

Risk vectors, aggregation, and future bump-and-revalue work need a stable taxonomy beyond opaque strings. The repository now defines frozen dataclasses for factor kinds while preserving string keys for API/DTO compatibility.

Evidence in repo:

- `backend/app/risk/factor_types.py`: `EquitySpot`, `EquityVol`, `RateZero`, `FXSpot`, `FXVol`; union `RiskFactor`; `FactorType = Literal["equity", "vol", "rate", "fx"]`.
- Stable string keys via `.key` (e.g. `{underlying}:VOL`, `{currency}:RATE`, `{pair}:VOL`) and `parse_risk_factor` for legacy `(factor, factor_type, bucket)` triples.
- `RiskFactorEngine` aggregates on typed `RiskFactor` instances; API DTO `RiskFactorExposure` still exposes `factor: str`.
- `ROADMAP.md` marks M1.6 complete with tests (`test_factor_types.py` and related).

## Decision

1. Internal risk-factor identity uses the typed **`RiskFactor`** union in `factor_types.py`.
2. Wire formats and existing exposure DTOs continue to use **string keys** derived from `.key` until a versioned API change is approved.
3. Factor types are limited to the four literals already in domain/API: equity, vol, rate, fx (equity vs FX vol distinguished by type/heuristic in `parse_risk_factor`).
4. Richer surface buckets (`expiry`, `moneyness` on vol types) may refine identity later without breaking the public string key convention until explicitly versioned.

## Alternatives considered

| Alternative | Why rejected (given current code) |
|-------------|-----------------------------------|
| Strings only forever | Insufficient for typed aggregation/sort keys; M1.6 already migrated the engine. |
| Break API to return structured factor objects immediately | Would be a cross-cutting contract break; Lead Architect has not approved it; DTO still uses `factor: str`. |
| Single generic `RiskFactor(key, type, bucket)` class | Current design prefers distinct frozen dataclasses per economic meaning. |

## Consequences

- Stress, sensitivities, and VaR contribution work should consume typed factors internally and map to strings only at the boundary.
- Adding a new economic factor family requires extending `FactorType` / the union and coordinating DTO/OpenAPI changes.
- Key-rate and surface work (M1.4 / M1.5 / M1.7) builds on this taxonomy rather than inventing parallel ID schemes.
