# Architecture Decision Records

This index lists accepted architecture decisions that are already evidenced in code or repository docs. Do not add ADRs for future ideas until the decision has been made and the implementation/docs evidence exists.

## Status Summary

| ADR | Status | Decision | Evidence |
|---|---|---|---|
| [`001-quantlib-for-pricing.md`](001-quantlib-for-pricing.md) | Accepted | QuantLib is the intended production pricing adapter behind `PricingEngine`; builtin remains the deterministic reference/fallback. | `backend/app/interfaces/pricing.py`, `backend/app/pricing/quantlib.py`, `backend/app/pricing/builtin.py` |
| [`002-immutable-market-snapshots.md`](002-immutable-market-snapshots.md) | Accepted | Market state is represented as immutable, copy-on-write `MarketSnapshot` payloads; curves and surfaces are consumed when attached. | `backend/app/domain/models.py`, `backend/app/market/`, pricing curve/surface helpers |
| [`003-typed-risk-factors.md`](003-typed-risk-factors.md) | Accepted | Internal risk-factor identity uses typed factor dataclasses while public DTOs keep stable string keys. | `backend/app/risk/factor_types.py`, risk factor tests |
| [`004-formal-scenario-domain-model.md`](004-formal-scenario-domain-model.md) | Accepted | Formal scenarios use typed shocks and adapters preserve legacy `StressScenario` endpoints. | `backend/app/risk/scenario_model.py`, `backend/app/api/scenario_wire.py` |
| [`005-sqlalchemy-persistence.md`](005-sqlalchemy-persistence.md) | Accepted | SQLAlchemy/Alembic persist JSON-serializable domain payloads; Postgres-backed risk-run workers claim with `SKIP LOCKED`. | `backend/app/persistence/`, `backend/app/services/risk_run_worker.py`, `scripts/smoke_postgres.sh` |
| [`006-llm-orchestrates-not-calculates.md`](006-llm-orchestrates-not-calculates.md) | Accepted | LLM/NL layers orchestrate deterministic risk tools and never calculate risk values themselves. | `backend/app/risk/query.py`, `docs/agents/09_AI_ORCHESTRATION_ENGINEER.md` |
| [`007-quantlib-concurrency.md`](007-quantlib-concurrency.md) | Accepted | QuantLib access is serialized inside a process; process isolation is preferred for parallel full revaluation; native kernels stay off QuantLib globals. R0.6.5: RiskRun / Compose worker is the HEAVY full-reval partition (no unused ProcessPoolExecutor). | `backend/app/pricing/quantlib.py`, `backend/app/services/risk_run_worker.py`, `backend/tests/test_r065_process_partition.py`, `backend/native/` |
| [`008-api-v1-canonical-and-legacy-sunset.md`](008-api-v1-canonical-and-legacy-sunset.md) | Accepted | `/api/v1` is canonical; legacy unversioned routes remain dual-mounted with deprecation headers until the sunset gate. | `backend/app/api/`, `docs/api/v1_canonical_and_legacy_sunset.md`, frontend `/api/v1` client |

## Not Yet ADRs

The following topics are documented elsewhere but are not separate ADRs yet because the current decisions are either covered by existing ADRs or remain future work:

- VaR methodology modes: documented in [`docs/methodology/README.md`](../methodology/README.md) as implemented behavior; no separate architectural choice beyond existing risk-engine design has been recorded.
- Scenario-kernel performance SLA: documented in [`docs/performance.md`](../performance.md), [`benchmarks/README.md`](../../benchmarks/README.md), and [`benchmarks/RESULTS.md`](../../benchmarks/RESULTS.md); the native/QuantLib boundary is covered by ADR 007.
- Redis/RQ or another external queue: explicitly deferred. Current durable claim safety is Postgres `SKIP LOCKED` under ADR 005.
- Full external LLM tool loop: not implemented. The deterministic guardrail is captured by ADR 006.
