# Wave B Subagent Rules

Roles:
- Quant Analytics Agent
- Backend/API Agent
- Frontend Visualization Agent
- UX/Product Agent
- QA/Mutation Agent
- Independent Reviewer

Every prompt specifies Scope, Invariants, Acceptance, Tests and Non-goals.

Do not parallelize agents changing the same analytics contract.
Freeze backend metric semantics before frontend work.
No duplicate drawdown/VaR/attribution math in browser.

Loop:
inspect → tracker IN_PROGRESS → narrow subagent → implement → focused tests → independent review → fix confirmed issues → retest → evidence → DONE.
