# ADR 002: Immutable market snapshots

- Status: Accepted — **recursive soft freeze via `MappingProxyType`**; IR pricing consumes ``curves`` / ``key_rates`` when attached; option pricing consumes ``vol_surfaces`` when attached
- Date: 2026-09-02
- Owners: Lead Architect; Market Data & Curves Engineer

## Context

Scenarios and sensitivities must revalue against alternate market states without mutating the base marks used by other calculations. The MVP treats market state as a snapshot object and produces shocked copies rather than in-place edits.

Evidence in repo:

- `MarketSnapshot` in `backend/app/domain/models.py` (`frozen=True` Pydantic model).
- Nested maps (`equity_spots`, `rates`, `key_rates`, `curves`, `vol_surfaces`, …) are **recursively** wrapped in `MappingProxyType` (lists become tuples) so nested in-place mutation raises `TypeError`.
- Typed APIs: `bump` / `apply` / `diff` / `content_hash`; `shock_snapshot` composes typed bumps.
- Sub-market views: `equity` / `rates_market` / `vol` / `fx` (`market/markets.py`).
- Curve / vol-surface scaffolds attach via copy-on-write (`attach_standard_usd_curves`, `attach_vol_surface`).
- Pricing: `pricing/curve_rates.py` + Builtin/QuantLib bond/swap paths; `pricing/surface_vol.py` for EQ/FX options.
- Sensitivities: `KEY_RATE_CURVES_CONSUMED_BY_PRICING=True` drives true tenor key-rate DV01 when pillars exist.

## Decision

1. Market state for pricing and risk is represented as a **`MarketSnapshot`**.
2. Shocks and bumps produce a **new** snapshot via `bump` / `apply` / `shock_snapshot` / `model_copy`; callers must not mutate shared snapshot fields in place.
3. Immutability is **enforced for nested payloads** by recursive `MappingProxyType` freeze (not only the top-level model). Accidental `snap.curves[name]["zeros"][tenor] = …` fails like a MappingProxy write.
4. Because Pydantic v2 `model_copy(update=...)` **skips** after validators, `MarketSnapshot.model_copy` is overridden to re-apply deep-freeze after every copy (attach/bump/shock paths).
5. Serialization / hashing use deep unfreeze to plain dict/list trees.
6. Live vendor feeds remain out of scope without Lead Architect approval; providers stay behind `MarketDataProvider`.
7. When `curves` / `key_rates` / `vol_surfaces` are attached, pricing **must** prefer them over flat scalars for the relevant instruments; scalars remain the fallback when payloads are absent.

## Rate bump convention (aligned with freeze / copy-on-write)

- `RateZero(ccy, "PARALLEL"|"ALL")`: parallel-shift scalar `rates[ccy]`, all `key_rates[ccy]` pillars, and matching curve zeros.
- `RateZero(ccy, "10Y")` (or other key tenor): update `key_rates` / curve zeros for that tenor only — **does not** silently parallel-shift `rates[ccy]`.

## Alternatives considered

| Alternative | Why rejected / deferred |
|-------------|-------------------------|
| Mutate positions’ trade marks for each shock | Couples scenario logic into instruments; harder to compare base vs shocked consistently. |
| Shallow MappingProxy only (mutable nested curve/vol dicts) | Allowed silent nested mutation; rejected after review — deep-freeze required. |
| Pass scenario deltas only into QuantLib without a snapshot object | Would skip the shared market abstraction used by Builtin, stress, and sensitivities. |

## Consequences

- New risk paths should shock via `bump` / `apply` / `shock_snapshot`, not in-place dict edits.
- Deep freeze + copy-on-write is the contract; do not reintroduce mutable nested dict aliases on the snapshot.
- Milestone 1 market-data + pricing-consumption acceptance is closed; remaining curve/vol work (bootstrap, SABR, caps/swaptions) is later-milestone enrichment, not a reopening of this ADR’s immutability decision.
