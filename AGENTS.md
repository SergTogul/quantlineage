# RiskForge Agent Operating Manual

This repository is developed by a coordinated set of specialized subagents. Each agent owns a bounded area of the architecture and must avoid making unrelated changes outside that area without an explicit handoff.

Cursor startup prompts and orchestration tips: `docs/agents/CURSOR_SETUP.md`. Workflow, DoD, and templates live under `docs/agents/`.

## Product mission

RiskForge is an institutional-style multi-asset portfolio and derivatives risk-management platform. Mature pricing libraries such as QuantLib provide instrument pricing; RiskForge owns portfolio aggregation, market snapshots, risk factors, VaR/Expected Shortfall, stress testing, reverse stress, P&L/risk attribution, limits, hierarchy, scenario computation, and the user workflow.

Core rule:

> The pricing library prices. RiskForge manages portfolio risk. The LLM orchestrates deterministic tools; it never calculates financial risk itself.

## Non-goals

Agents must not:

- replace QuantLib or invent a general pricing library;
- compute or invent risk/pricing numbers in LLM prompts or model output;
- duplicate pricing/risk formulas in the UI or transport layer;
- introduce live market-data vendor integrations without Lead Architect approval;
- change numerical methodology solely for performance.

## Team structure

| Agent | Primary ownership | Must not own |
|---|---|---|
| Lead Architect / Orchestrator | architecture, task decomposition, integration, ADRs | detailed quant implementation unless integration requires it |
| Quant Pricing Engineer | instruments, QuantLib adapters, valuation/Greeks | portfolio VaR, UI, persistence |
| Market Data & Curves Engineer | snapshots, curves, vol surfaces, factor taxonomy | pricing workflow, VaR algorithms |
| Portfolio Risk Engineer | VaR, ES, incremental/component risk, aggregation | instrument pricing internals |
| Stress & Scenario Engineer | scenario model, historical/hypothetical/reverse stress, contribution | generic VaR engine |
| C++ Performance Engineer | native kernels, benchmarks, profiling, concurrency | business rules, API semantics |
| Backend/API Engineer | FastAPI, services, persistence boundaries, error model | quant formulas |
| Frontend/Risk UX Engineer | React risk terminal, scenario builder, drill-down, visualizations | backend quant logic |
| AI Orchestration Engineer | deterministic tool schemas, NL routing, agent evals | numerical pricing/risk calculations |
| QA & Quant Validation Engineer | test strategy, golden tests, invariants, E2E, validation | feature ownership |
| DevOps/Platform Engineer | CI, containers, reproducibility, build tooling | product/quant logic |

Detailed charters are in `docs/agents/`. See also `TEAM_STRUCTURE.md`, `WORKFLOW.md`, and `DEFINITION_OF_DONE.md`.

### Choosing an owner

Assign exactly one owner per task. If ownership is unclear or a change spans two areas, the Lead Architect assigns the owner and any handoffs. Never dual-own the same file set in parallel.

### Ownership → code map

| Area | Typical paths |
|---|---|
| Shared contracts / domain | `backend/app/domain/`, `backend/app/interfaces/` (Lead Architect approves cross-cutting changes) |
| Quant pricing | `backend/app/pricing/` |
| Market data & factors | `backend/app/market/`, `backend/app/risk/factors.py` |
| Portfolio risk | `backend/app/risk/var.py`, `historical.py`, `hierarchy.py`, `attribution.py`, `limits.py`, `backend/app/compute/` |
| Stress & scenarios | `backend/app/risk/stress.py` |
| C++ / native | `backend/native/`, ctypes bridge in `backend/app/compute/` |
| Backend / API | `backend/app/main.py`, `backend/app/services/`, API DTOs/wiring |
| NL query / AI tools | `backend/app/risk/query.py` (and future tool-schema modules) |
| Frontend | `frontend/` |
| QA fixtures / cross-module tests | `backend/tests/`, `frontend/**/*.test.*` (with feature owner) |
| DevOps | `docker-compose.yml`, CI configs, `BUILD_NOTES.md`, toolchain docs |

Paths evolve; when in doubt, follow the charter and escalate boundary conflicts.

## Rules all agents must follow

1. Read `README.md`, `ROADMAP.md`, `BUILD_NOTES.md`, this file, and the relevant agent charter before changing code. Use `docs/agents/CURSOR_SETUP.md` when starting a Lead or specialist session.
2. Do not silently refactor code owned by another agent. Open a handoff/task instead.
3. Preserve interfaces unless the Lead Architect approves a breaking change.
4. Every behavior change requires tests in the same change.
5. Run the smallest relevant test suite during development and the full affected suite before handoff.
6. The handoff condition is **all tests pass**: all applicable/affected suites required by the task must pass, with exact commands/results recorded and no unexplained failures or skips.
7. The push condition is **CI is green**. Before the initial branch push, run all applicable local checks. The initial push may be needed to trigger CI; after CI starts, do not declare the push or handoff complete or continue integration until all required CI checks are green. If CI fails, fix the issue, rerun the applicable local checks, push the fix, and verify that required CI is green.
8. Quant changes require numerical tolerances and an explanation of the reference or invariant used.
9. UI code must not duplicate pricing/risk formulas.
10. LLM/AI code must call deterministic APIs and must not invent or compute risk numbers.
11. C++ optimizations must have a Python/reference implementation and benchmark evidence.
12. Add an ADR for important architectural decisions.
13. Keep commits/task batches narrow enough to review.

## Required completion report

A task is done only when `docs/agents/DEFINITION_OF_DONE.md` is satisfied.

Every agent must end a task with:

- Summary of changes
- Files changed
- Tests added/updated
- Exact test commands executed
- Test results
- Known limitations/risks
- Any handoff needed from another agent

Use `docs/agents/HANDOFF_TEMPLATE.md`.

## Escalation rules

Escalate to the Lead Architect when:

- an interface must change across modules;
- a change affects more than two ownership areas;
- a new dependency is introduced;
- a numerical convention is ambiguous;
- performance optimization would alter results or precision;
- API compatibility would break;
- a test reveals conflicting business/quant expectations.

## Merge order for cross-agent work

1. Architecture/interface contract
2. Reference implementation
3. Quant validation/tests
4. API integration
5. UI integration
6. Native optimization
7. AI orchestration
8. E2E/CI verification
