from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union
from pydantic import BaseModel, Field, model_validator


class AssetClass(str, Enum):
    EQUITY = "equity"
    RATES = "rates"
    FX = "fx"


class EquityPosition(BaseModel):
    type: Literal["equity"]
    id: str
    symbol: str
    quantity: float
    price: float
    sector: str = "Other"
    book: str = "Equity"


class EquityFuturePosition(BaseModel):
    type: Literal["equity_future"]
    id: str
    symbol: str
    quantity: float
    spot: float
    multiplier: float = 50.0
    maturity_years: float = Field(default=0.25, gt=0)
    risk_free_rate: float = 0.04
    dividend_yield: float = 0.0
    sector: str = "Index"
    book: str = "Equity Derivatives"


class EuropeanOptionPosition(BaseModel):
    type: Literal["european_option"]
    id: str
    symbol: str
    quantity: float
    spot: float
    strike: float
    maturity_years: float = Field(gt=0)
    volatility: float = Field(gt=0)
    risk_free_rate: float = 0.04
    dividend_yield: float = 0.0
    option_type: Literal["call", "put"]
    sector: str = "Other"
    book: str = "Equity Derivatives"


class BondPosition(BaseModel):
    type: Literal["bond"]
    id: str
    issuer: str
    face_value: float = Field(gt=0)
    quantity: float = 1.0
    maturity_years: float = Field(gt=0)
    yield_rate: float
    duration: float = Field(gt=0)
    currency: str = "USD"
    book: str = "Rates"


class SwapPosition(BaseModel):
    type: Literal["swap"]
    id: str
    currency: str = "USD"
    notional: float = Field(gt=0)
    maturity_years: float = Field(gt=0)
    fixed_rate: float
    market_swap_rate: float
    pay_fixed: bool = True
    duration: float = Field(gt=0)
    book: str = "Rates Derivatives"


class FXForwardPosition(BaseModel):
    type: Literal["fx_forward"]
    id: str
    pair: str
    notional_base: float
    spot: float = Field(gt=0)
    strike: float = Field(gt=0)
    maturity_years: float = Field(gt=0)
    domestic_rate: float = 0.04
    foreign_rate: float = 0.03
    book: str = "FX"


class FXOptionPosition(BaseModel):
    type: Literal["fx_option"]
    id: str
    pair: str
    notional_base: float
    spot: float = Field(gt=0)
    strike: float = Field(gt=0)
    maturity_years: float = Field(gt=0)
    volatility: float = Field(gt=0)
    domestic_rate: float = 0.04
    foreign_rate: float = 0.03
    option_type: Literal["call", "put"]
    book: str = "FX Derivatives"


Position = Annotated[
    Union[
        EquityPosition,
        EquityFuturePosition,
        EuropeanOptionPosition,
        BondPosition,
        SwapPosition,
        FXForwardPosition,
        FXOptionPosition,
    ],
    Field(discriminator="type"),
]


class Portfolio(BaseModel):
    id: str
    name: str
    positions: list[Position]
    desk: str = "Global Macro"
    strategy: str = "Multi-Asset"

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [p.id for p in self.positions]
        if len(ids) != len(set(ids)):
            raise ValueError("position ids must be unique")
        return self


class MarketSnapshot(BaseModel):
    id: str = "current"
    as_of: str = "current"
    equity_spots: dict[str, float] = {}
    equity_vols: dict[str, float] = {}
    fx_spots: dict[str, float] = {}
    fx_vols: dict[str, float] = {}
    rates: dict[str, float] = {"USD": 0.04}
    key_rates: dict[str, dict[str, float]] = {}


class Valuation(BaseModel):
    position_id: str
    market_value: float
    delta: float = 0.0
    gamma: float = 0.0
    vega: float = 0.0
    dv01: float = 0.0
    fx_delta: float = 0.0


class RiskSummary(BaseModel):
    portfolio_id: str
    market_value: float
    delta: float
    gamma: float
    vega: float
    dv01: float
    fx_delta: float = 0.0
    var_95: float
    var_99: float
    expected_shortfall_99: float


class RiskFactorExposure(BaseModel):
    factor: str
    factor_type: Literal["equity", "vol", "rate", "fx"]
    bucket: str
    exposure: float


class ScenarioKind(str, Enum):
    FACTOR = "factor"
    MACRO = "macro"
    HISTORICAL_STYLE = "historical_style"
    CUSTOM = "custom"
    REVERSE = "reverse"


class StressScenario(BaseModel):
    id: str | None = None
    name: str
    description: str = ""
    kind: ScenarioKind = ScenarioKind.FACTOR
    horizon: str = "instant"
    equity_shock: float = 0.0
    vol_shock: float = 0.0
    rates_shift_bps: float = 0.0
    fx_shock: float = 0.0
    equity_shocks: dict[str, float] = {}
    vol_shocks: dict[str, float] = {}
    rate_shocks_bps: dict[str, float] = {}
    fx_shocks: dict[str, float] = {}
    max_loss_pct: float | None = Field(default=None, gt=0)


class StressResult(BaseModel):
    scenario: str
    pnl: float
    by_position: dict[str, float]


class PositionStressContribution(BaseModel):
    position_id: str
    pnl: float
    contribution_pct: float


class StressEvaluation(BaseModel):
    scenario_id: str
    scenario: str
    kind: ScenarioKind
    description: str
    base_market_value: float
    stressed_market_value: float
    pnl: float
    loss: float
    loss_pct_nav: float
    threat_level: Literal["LOW", "MODERATE", "HIGH", "SEVERE"]
    breached: bool
    max_loss_pct: float | None = None
    by_position: dict[str, float]
    top_loss_contributors: list[PositionStressContribution]


class ScenarioEvaluationReport(BaseModel):
    portfolio_id: str
    base_market_value: float
    worst_scenario: str | None
    worst_loss: float
    severe_count: int
    breach_count: int
    evaluations: list[StressEvaluation]


class CustomStressRequest(BaseModel):
    portfolio: Portfolio
    scenarios: list[StressScenario]


class ReverseStressRequest(BaseModel):
    portfolio: Portfolio
    target_loss_pct: float = Field(gt=0)
    factor: Literal["equity", "rates", "vol", "fx"] = "equity"
    max_shock: float = Field(default=0.80, gt=0)


class ReverseStressResult(BaseModel):
    factor: str
    target_loss_pct: float
    required_shock: float | None
    achieved_loss_pct: float
    converged: bool


class ScenarioComparisonRequest(BaseModel):
    portfolio: Portfolio
    hedged_portfolio: Portfolio
    scenarios: list[StressScenario]


class ScenarioComparison(BaseModel):
    scenario: str
    base_pnl: float
    hedged_pnl: float
    improvement: float


class Contributor(BaseModel):
    position_id: str
    label: str
    risk_amount: float
    contribution_pct: float


class RiskLimit(BaseModel):
    metric: Literal["var_99", "dv01", "vega", "single_position_pct"]
    limit: float


class LimitResult(BaseModel):
    metric: str
    value: float
    limit: float
    utilization_pct: float
    breached: bool


class VaRMethodResult(BaseModel):
    method: Literal["historical", "parametric"]
    confidence: float
    var: float
    expected_shortfall: float


class RiskContribution(BaseModel):
    position_id: str
    component_var: float
    contribution_pct: float


class VaRReport(BaseModel):
    portfolio_id: str
    methods: list[VaRMethodResult]
    contributions: list[RiskContribution]


class HierarchyNode(BaseModel):
    name: str
    level: Literal["portfolio", "desk", "strategy", "book", "trade"]
    market_value: float
    var_99: float
    children: list["HierarchyNode"] = []


class AttributionItem(BaseModel):
    driver: str
    pnl: float


class AttributionReport(BaseModel):
    base_market_value: float
    current_market_value: float
    total_change: float
    explained_change: float
    residual: float
    items: list[AttributionItem]


class AttributionRequest(BaseModel):
    previous_portfolio: Portfolio
    current_portfolio: Portfolio
    previous_market: MarketSnapshot | None = None
    current_market: MarketSnapshot | None = None


class RiskQueryRequest(BaseModel):
    portfolio: Portfolio
    question: str


class RiskQueryResponse(BaseModel):
    intent: str
    answer: str
    data: dict
