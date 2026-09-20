# Cursor Cloud kickoff prompt

Copy this into a Cursor Cloud Agent running on the PR #6 head branch.

```text
You are the root implementation agent for the QuantLineage Grounded Conversational Risk Assistant.

Repository:
https://github.com/SergTogul/quantlineage

Starting branch:
cursor/risk-query-incomplete-fallback-bebd

Before doing anything:

1. Inspect git status and preserve all existing work.
2. Read every applicable AGENTS.md or repository instruction file.
3. Read these files completely:
   - docs/ai/CONVERSATIONAL_ASSISTANT_GOAL.md
   - docs/ai/CONVERSATIONAL_ASSISTANT_TASKS.md
   - docs/adr/006-llm-orchestrates-not-calculates.md
   - docs/ai/openai_risk_assistant_design.md
4. Inspect the current PR diff against its base.
5. Do not use destructive git commands.
6. Do not push, merge, retarget, or open another PR unless explicitly requested.

Run exactly one loop iteration: C00 only.

Use subagents:

- Spawn an architecture-auditor subagent to trace UI → API → provider → tool → formatter and identify any request labeled model-routed without a model call.
- Spawn an OpenAI-loop auditor subagent to trace one-shot and bounded Responses behavior, including function_call_output continuation and turn-budget semantics.
- Spawn a quant-tools auditor subagent to inspect get_position_greeks, option filtering, units, conventions, and provenance.
- Spawn a security-grounding auditor subagent to inspect exception handling, model-visible errors, numeric grounding, secret handling, and fallback replay.

All C00 subagents are read-only. They must not edit files, commit, update task state, or begin C01. Ask each to return concise findings with file/line references and recommended severity.

As root:

1. Reproduce the current one-shot behavior.
2. Reproduce bounded behavior with AI_MAX_TOOL_ROUNDS=2.
3. Prove whether Greek questions call OpenAI.
4. Run the exact C00 checks, correcting only test paths/commands that differ from the repository.
5. Synthesize subagent results.
6. Make no product-code changes.
7. If C00 passes, mark only C00 complete in CONVERSATIONAL_ASSISTANT_TASKS.md and add evidence:
   - commands and results;
   - runtime flow;
   - model-call counts;
   - metadata mismatches;
   - conversation-state behavior;
   - subagent findings;
   - commit SHA if available.
8. If the baseline is red for an unrelated reason, mark C00 blocked, document the blocker, and stop.
9. Commit only the C00 evidence update with a focused message.
10. Stop after C00.

Final response must contain:

- selected task;
- subagents used and their findings;
- files inspected;
- commands and results;
- files changed;
- commit SHA;
- blockers;
- next eligible task, without starting it.
```

## Subsequent loop prompt

After C00, use this shorter prompt for each run:

```text
Read docs/ai/CONVERSATIONAL_ASSISTANT_GOAL.md and
docs/ai/CONVERSATIONAL_ASSISTANT_TASKS.md completely.

Execute exactly one loop iteration: select the first unchecked task whose
dependencies are complete.

Use the task's recommended subagents. Give each subagent a non-overlapping,
explicit scope. Subagents must not update task status or begin another task.
The root agent owns integration, tests, evidence, and the final focused commit.

Meet every acceptance criterion, run every scoped check, record evidence in the
task, commit, and stop. If blocked, record the blocker and stop. Preserve
unrelated changes and do not push or merge unless explicitly requested.

Report the completed task, subagent contributions, checks, files changed,
commit SHA, blockers, and next eligible task.
```
