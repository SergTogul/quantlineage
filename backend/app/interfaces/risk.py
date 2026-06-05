from abc import ABC, abstractmethod

from app.domain.models import Portfolio, RiskSummary
from app.interfaces.pricing import PricingEngine


class RiskEngine(ABC):
    @abstractmethod
    def calculate(self, portfolio: Portfolio, pricing_engine: PricingEngine) -> RiskSummary:
        raise NotImplementedError
