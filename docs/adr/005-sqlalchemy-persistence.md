# ADR 005: SQLAlchemy / Alembic persistence (no QuantLib runtime objects)

- Status: Accepted (schema + repos; FastAPI DI **DONE**; stress HTTP ← scenario_definitions DI **DONE**; Compose worker + Postgres `SKIP LOCKED` claim **DONE**; Postgres CI smoke green; Redis/RQ deferred)
- Date: 2026-09-02
- Owners: Backend/API Engineer; DevOps/Platform Engineer

## Context

QuantLineage needs durable storage for portfolios, trades, market snapshots,
scenario definitions, risk runs/results, and limit definitions. Pricing uses
QuantLib at runtime; those handles are not serializable and must not be stored.

## Decision

1. Introduce a dedicated package ``backend/app/persistence/`` (ORM models,
 session/config, repository interfaces + SQLAlchemy implementations).
2. Use **SQLAlchemy 2.0** + **Alembic** for schema migrations.
3. Prefer **PostgreSQL** in Compose / production via
 ``QUANTLINEAGE_DATABASE_URL=postgresql+psycopg://quantlineage:quantlineage@…/quantlineage``.
4. Unit tests use **SQLite** (``create_all`` and/or Alembic upgrade) so live
 Postgres is not required for the default pytest suite. CI also runs a
 dedicated ``postgres-smoke`` job (service container +
 ``scripts/smoke_postgres.sh``) to exercise the psycopg path.
5. Persist only **JSON-serializable** domain payloads (`model_dump`, snapshot
 trees). Never store QuantLib curves, processes, or engine instances.
6. Market snapshots split **metadata** (`as_of`, `content_hash`, `meta`) from
 **data** (full marks JSON).
7. Risk-run status enum lives in domain ``RiskRun`` / ``RiskRunStatus``
 (``QUEUED`` / ``RUNNING`` / ``COMPLETED`` / ``FAILED``). ORM re-exports the
 same enum. Lifecycle service is ; async HTTP APIs are .
8. Alembic revisions live under ``backend/migrations/`` (``alembic.ini``
 ``script_location = migrations``) so the package path does not shadow the
 installed ``alembic`` distribution.

## Alternatives considered

| Alternative | Why rejected / deferred |
|-------------|-------------------------|
| ORM inside ``app/risk/`` | Couples risk agents to DB churn; charter prefers persistence boundary. |
| Persist QuantLib handles | Not portable across process restart; violates pricing-adapter rule. |
| Require Postgres for every unit test | Slower / flakier; SQLite covers schema + repo contracts; dedicated CI job covers psycopg. |
| Redis/RQ for MVP risk runs | Deferred: Postgres `FOR UPDATE SKIP LOCKED` already provides multi-worker claim safety. Redis/RQ should only be introduced with real product/ops semantics such as priority, tenancy, retries, or queue observability. |

## Consequences

- FastAPI DI ( **DONE**): when ``QUANTLINEAGE_DATABASE_URL`` is set, lifespan
 builds a SQLAlchemy session factory, seeds ``SAMPLE_PORTFOLIO``, a sample
 market snapshot (``position_marks``), ``DEFAULT_SCENARIOS`` +
 ``THREAT_SCENARIOS``, and ``DEFAULT_LIMITS``, and wires
 ``RiskRunWorker(session_factory=…)``. ``Depends`` exposes
 ``get_market_snapshot_repository``, ``get_scenario_definition_repository``,
 ``get_limit_definition_repository``, plus portfolio / snapshot loaders and
 the risk-run worker. When unset, in-memory repos (pre-seeded) + sample
 portfolio remain the default (unit tests unchanged).
- Stress HTTP ( **DONE**): ``GET /risk/stress/scenarios`` and default
 ``POST /risk/stress/evaluate`` resolve scenarios through
 ``get_default_stress_scenarios`` (DI repo ``list_all``; missing/empty →
 ``THREAT_SCENARIOS`` fallback). ``POST /risk/stress`` uses
 ``get_baseline_stress_scenarios`` (DEFAULT-id filter on that list; empty →
 ``DEFAULT_SCENARIOS``). Custom evaluate / compare paths still take
 request-body scenarios.
- Alembic initial revision: ``001_initial_persistence``; append-only
 ``002_risk_run_domain_fields`` (``pricing_engine_version``, ``methodology``,
 ``scenario_set``). Scripts under ``backend/migrations/``.
- Compose adds ``postgres``, ``backend``, ``worker``, and ``frontend``.
- ** (DONE):** Compose ``worker`` runs ``python -m app.worker`` (same
 ``RiskRunWorker`` + SQLAlchemy session factory as API lifespan). ``poll_once``
 calls ``claim_queued``: on PostgreSQL, ``SELECT … FOR UPDATE SKIP LOCKED``
 then QUEUED→RUNNING so concurrent workers do not race; SQLite/unit path uses
 FIFO claim without skip-locked. Backend sets ``QUANTLINEAGE_EXTERNAL_WORKER=1``
 so HTTP enqueues only. Local/default remains in-process ``ThreadPoolExecutor``.
 Redis/RQ not required for claim safety. Compose ships one worker by default.
- Apply Alembic before first use: ``alembic upgrade head`` (or
 ``docker compose run --rm backend alembic upgrade head``).
- Local / CI Postgres smoke: ``./scripts/smoke_postgres.sh`` (requires
 ``QUANTLINEAGE_DATABASE_URL``). GitHub-hosted runner evidence is recorded in
 ``ROADMAP.md``.
