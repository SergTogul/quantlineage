# Using the RiskForge Subagents in Cursor

## Recommended setup

Keep `AGENTS.md` at the repository root so every coding session starts with the shared operating rules. Keep specialist charters under `docs/agents/`.

When starting a subagent, give it the matching charter and a task created from `TASK_TEMPLATE.md`.

## Lead-agent startup prompt

> Read `AGENTS.md`, `README.md`, `TASKS.md`, `BUILD_NOTES.md`, `docs/agents/TEAM_STRUCTURE.md`, `docs/agents/WORKFLOW.md`, and `docs/agents/DEFINITION_OF_DONE.md`. You are the Lead Architect. Inspect the repository first. Break the requested workstream into small tasks, assign each to exactly one specialist agent, identify dependencies and interface contracts, and define acceptance criteria/tests. Parallelize only tasks with stable contracts. Do not let subagents make unrelated refactors.

## Specialist-agent startup pattern

> Read `AGENTS.md`, `docs/agents/<YOUR_CHARTER>.md`, `docs/agents/WORKFLOW.md`, `docs/agents/DEFINITION_OF_DONE.md`, and the assigned task. Inspect relevant code and tests before editing. Stay inside your ownership boundary. Add tests with every change and execute them. At completion, provide a handoff using `docs/agents/HANDOFF_TEMPLATE.md`; all applicable/affected suites required by the task must pass, with exact commands/results recorded and no unexplained failures or skips.

## Recommended orchestration loop

1. Lead Architect creates 2–4 bounded tasks.
2. Start independent specialists in parallel.
3. Each specialist returns a handoff report.
4. QA validates quantitative/integration behavior.
5. Lead integrates and resolves conflicts.
6. DevOps runs reproducibility/build matrix if environment/config changed.
7. Complete a push/handoff or continue integration only after Definition of Done passes and required CI checks are green; an initial branch push may be used to trigger CI after all applicable local checks pass.

## Good parallel batch example

### Batch A
- Market Data agent: typed `RiskFactor` model.
- DevOps agent: local/CI QuantLib environment.
- Frontend agent: shell/navigation cleanup only, against unchanged APIs.

### Batch B after RiskFactor contract is merged
- Portfolio Risk agent: key-rate/vol/FX factor aggregation.
- Stress agent: typed factor shocks.
- Quant Pricing agent: remaining QuantLib adapters.

### Batch C
- Backend agent: expose new factor/scenario contracts.
- QA agent: reconciliation and golden/invariant tests.

### Batch D
- Frontend agent: factor heatmaps/scenario builder integration.
- C++ agent: optimize only benchmarked risk kernels.

### Batch E
- AI agent: expose deterministic tools after APIs stabilize.

## Avoid these patterns
- Multiple agents editing the same core model simultaneously.
- Frontend agent inventing API response fields.
- Stress agent modifying QuantLib pricing code.
- C++ agent changing methodology to gain speed.
- AI agent implementing formulas in prompts.
- Lead agent doing all specialist coding itself.

