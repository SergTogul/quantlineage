from __future__ import annotations
from app.domain.models import Portfolio, RiskQueryResponse


class RiskQueryEngine:
    """Deterministic query router. An LLM can later call the same service methods as tools."""
    def answer(self, question: str, portfolio: Portfolio, service) -> RiskQueryResponse:
        q=question.lower()
        if "worst" in q and ("stress" in q or "scenario" in q or "threat" in q):
            r=service.threat_evaluation(portfolio); w=r.evaluations[0] if r.evaluations else None
            return RiskQueryResponse(intent="worst_scenario",answer=f"Worst scenario is {w.scenario} with loss {w.loss:,.0f}." if w else "No scenarios configured.",data=w.model_dump() if w else {})
        if "contribut" in q or "biggest risk" in q or "top risk" in q:
            x=service.contributors(portfolio)[:5]
            return RiskQueryResponse(intent="contributors",answer="Top risk contributors: "+", ".join(f"{i.label} {i.contribution_pct:.1f}%" for i in x),data={"contributors":[i.model_dump() for i in x]})
        if "var" in q or "expected shortfall" in q:
            r=service.summary(portfolio)
            return RiskQueryResponse(intent="var",answer=f"99% VaR is {r.var_99:,.0f}; 99% Expected Shortfall is {r.expected_shortfall_99:,.0f}.",data=r.model_dump())
        if "limit" in q or "breach" in q:
            x=service.limits(portfolio); b=[i for i in x if i.breached]
            return RiskQueryResponse(intent="limits",answer=f"{len(b)} limit breaches." if b else "No limit breaches.",data={"limits":[i.model_dump() for i in x]})
        return RiskQueryResponse(intent="summary",answer="I can answer VaR/ES, limits, top contributors, and worst stress scenario using deterministic risk APIs.",data=service.summary(portfolio).model_dump())
