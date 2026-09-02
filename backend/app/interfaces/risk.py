from abc import ABC, abstractmethod
from app.domain.models import Portfolio
from app.interfaces.pricing import PricingEngine


class RiskEngine(ABC):
    @abstractmethod
    def calculate(self, portfolio: Portfolio, pricing_engine: PricingEngine) -> dict[str, float]:
        raise NotImplementedError
