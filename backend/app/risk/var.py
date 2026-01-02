from __future__ import annotations
import math
from statistics import NormalDist
import numpy as np
from app.domain.models import Portfolio, RiskContribution, VaRMethodResult, VaRReport
from app.interfaces.pricing import PricingEngine


class VaRAnalytics:
    def __init__(self, seed: int = 7, observations: int = 750):
        self.seed, self.observations = seed, observations

    def _factor_history(self):
        rng=np.random.default_rng(self.seed)
        return rng.normal(0.0002,0.013,self.observations), rng.normal(0,0.07,self.observations), rng.normal(0,7,self.observations), rng.normal(0,0.006,self.observations)

    def _position_pnls(self, portfolio: Portfolio, pricing: PricingEngine):
        er, vp, rb, fx = self._factor_history()
        out={}
        for p in portfolio.positions:
            v=pricing.value(p)
            out[p.id] = v.delta*er + .5*v.gamma*er*er + v.vega*(vp*100) + v.dv01*rb + v.fx_delta*fx
        return out

    def report(self, portfolio: Portfolio, pricing: PricingEngine, confidence: float = .99) -> VaRReport:
        pos=self._position_pnls(portfolio,pricing); total=sum(pos.values(), start=np.zeros(self.observations)); losses=-total
        var=float(max(0,np.quantile(losses,confidence))); tail=losses[losses>=var]; es=float(max(var,tail.mean() if len(tail) else var))
        sd=float(np.std(total,ddof=1)); z=NormalDist().inv_cdf(confidence); pvar=max(0,z*sd)
        # Normal ES: sigma * phi(z)/(1-alpha)
        pes=max(pvar, sd*(math.exp(-.5*z*z)/math.sqrt(2*math.pi))/(1-confidence))
        # Component VaR from covariance with portfolio P&L; sums to parametric VaR.
        variance=float(np.var(total,ddof=1)); contributions=[]
        for pid,pnl in pos.items():
            cov=float(np.cov(pnl,total,ddof=1)[0,1]) if variance>0 else 0
            component=pvar*cov/variance if variance>0 else 0
            contributions.append(RiskContribution(position_id=pid,component_var=component,contribution_pct=component/pvar*100 if pvar else 0))
        contributions.sort(key=lambda x: abs(x.component_var),reverse=True)
        return VaRReport(portfolio_id=portfolio.id,methods=[
            VaRMethodResult(method="historical",confidence=confidence,var=var,expected_shortfall=es),
            VaRMethodResult(method="parametric",confidence=confidence,var=pvar,expected_shortfall=pes),
        ],contributions=contributions)
