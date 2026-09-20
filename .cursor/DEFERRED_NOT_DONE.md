# Deferred tasks status (updated 2026-09-20)

T20–T24 were historically labeled “deferred” and were **not** complete until checked.

**Current status:** T20–T24 are checked with evidence in `docs/ai/TASKS.md`.

- T20 RiskAssistant protocol
- T21 Bounded Responses tool loop
- T22 Numeric narration grounding
- T23 Multi-tool investigation evals
- T24 QuantLib tools design eval (`docs/ai/T24_QUANTLIB_TOOLS_EVAL.md`)

Optional follow-ups (not blocking the PR#4 task queue):

- Wire `BoundedRiskAssistant` into HTTP `answer_with_model` when `AI_MAX_TOOL_ROUNDS > 1`
- Implement `get_position_greeks` per the T24 decision (separate change)
