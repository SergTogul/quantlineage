# ADR 006: LLM orchestrates; deterministic engines calculate

- Status: Accepted (operating rule + partial implementation)
- Date: 2026-09-02
- Owners: Lead Architect; AI Orchestration Engineer

## Context

Natural-language risk questions are a product goal (Workstream 11), but LLMs must not invent prices, VaR, Greeks, stress P&L, or limit breaches. The MVP already routes NL questions through a deterministic keyword engine that calls portfolio service methods.

Evidence in repo:

- Product rule: the model orchestrates deterministic tools; it never calculates financial risk itself.
- No risk/pricing numbers are computed in LLM prompts or model output; AI code must call deterministic APIs.
- `backend/app/risk/query.py`: `RiskQueryEngine` — keyword intent router; docstring states an LLM can later call the same service methods as tools.
- `POST /risk/query` wires through `PortfolioService` → `RiskQueryEngine.answer(...)`, which invokes `threat_evaluation`, `contributors`, `summary`, `limits`, etc.

## Decision

1. All numerical risk and pricing results originate from **deterministic** QuantLineage/QuantLib code paths (services, risk engines, `PricingEngine`).
2. NL / LLM layers may only **select tools, bind arguments, and format grounded answers** from tool/API results.
3. The existing `RiskQueryEngine` is the interim deterministic router; a future LLM must call the same (or schema-equivalent) service tools, not replace them with model arithmetic.
4. Missing or ambiguous inputs must yield explicit uncertainty / refusal behavior (target for ), never fabricated numbers.

## Alternatives considered

| Alternative | Why rejected |
|-------------|--------------|
| LLM computes VaR/Greeks/stress in-prompt | Violates product non-goals and validation/reproducibility requirements. |
| Skip NL entirely | Product roadmap includes AI Risk Assistant; rule constrains *how*, not *whether*. |
| LLM returns numbers without tool calls, then “explain” | Same hallucination risk; evaluations require grounded tool use. |

## Consequences

- AI Orchestration work is blocked on stable tool contracts ( → ), not on embedding formulas in prompts.
- Frontend and docs must not present LLM-generated figures as authoritative without a deterministic source.
- Keyword `RiskQueryEngine` remains valid until replaced by tool-calling orchestration that preserves this ADR.
- Any proposal for the model to “estimate” risk when tools fail is a rejected design under this decision.
