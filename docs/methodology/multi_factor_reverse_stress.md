# Multi-factor reverse stress

Status: Published for users and interviewers.

**Code:** `backend/app/risk/reverse_stress_multi.py` (`MultiFactorReverseStressEngine`)

**API:** `POST /risk/stress/reverse/multi` and `POST /api/v1/risk/stress/reverse/multi`

This document states what the solver **does** and what it **is not**. Do not describe the result as a certified global optimum or a complete risk optimizer.

## Question answered

Given a portfolio and a target loss as a fraction of `|NAV|`, find a joint adverse move across selected factor families (`equity`, `rates`, `vol`, `fx`) that reaches at least that loss, preferring smaller shocks under an L2 box-normalized objective.

## Loss definition

- `pnl` = shocked portfolio MV − base MV (via `PricingEngine` + `MarketSnapshot.apply`)
- `loss = max(0, -pnl)`
- `loss_pct = loss / |base_mv|` (denom `1.0` if base MV is zero)

Target comparison uses the public `target_loss_pct` against this `loss_pct`.

## Adverse orthant (fixed directions)

Same convention as single-factor reverse stress :

| Family | Adverse direction | Wire units |
|--------|-------------------|------------|
| equity | relative spot **down** | relative |
| fx | relative spot **down** | relative |
| vol | relative vol level **up** | relative |
| rates | parallel zero **up** | basis points (bp) |

Only the adverse orthant is searched. Opposite-direction or mixed-sign solutions are out of scope.

## Objective

Minimize `‖u‖₂` where `u_i = s_i / max_i`, `s_i` is the internal search magnitude for family `i`, and `max_i` is the per-family bound (`0 ≤ u_i ≤ 1`). Equivalent to minimizing √(Σ u_i²) subject to `loss_pct ≥ target`.

Default families: equity, rates, vol, fx. Optional weights rescale the ray direction (normalized over selected families).

## Algorithm (deterministic)

1. **Zero-shock check** — if target already met, return zero shocks (`converged=True`).
2. **Feasibility at the box corner** — all selected families at max. If still below target, return corner shocks with `converged=False` and an explicit unreachable message.
3. **Ray search** — binary search scale ∈ [0, 1] along the non-negative weighted direction to a feasible point.
4. **Coordinate descent** — for each family, binary-search the smallest magnitude that keeps loss ≥ target with others fixed; repeat for a fixed number of passes until L2 stalls.

`method` on the result is always `ray_search_coordinate_descent`. Iteration caps and loss tolerance are fixed defaults (see module). **No RNG.**

Assumptions echoed on every result payload (`assumptions: string[]`) match the `ASSUMPTIONS` constant in code.

## What this is not

- **Not a certified global optimum.** Greedy refinement from the ray solution; other feasible points with smaller L2 may exist.
- **Not a proof of monotonicity.** Loss is **assumed monotone** (non-decreasing) in each adverse magnitude. That is not guaranteed for every book (e.g. short gamma, mixed hedges). Binary search can misbehave if that assumption fails.
- **Not a full-market reverse stress.** Families are coarse buckets (all equities together, parallel rates, etc.), not per-name / per-tenor optimization.
- **Not a substitute for scenario design.** Crisis library / hypothetical scenarios remain separate products; reverse stress answers a constrained “how bad must these buckets get” question only.

## Interviewer / recruiter one-liner

> Multi-factor reverse stress uses a deterministic ray search plus coordinate descent in the adverse orthant under an L2 box constraint. It returns documented assumptions on every result and is **not** claimed as a global optimizer.

## Related

- Single-factor reverse stress: `backend/app/risk/reverse_stress.py`
- Formal scenario shocks: `backend/app/risk/scenario_model.py`
- Broader methodology package: [`README.md`](README.md)
- Known limitations catalog: [`../known_limitations.md`](../known_limitations.md)
