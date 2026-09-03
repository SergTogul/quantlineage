"""In-code demo portfolios and their explicit market snapshots.

No live market-data vendor feeds. Legacy positions retain synthetic sample marks,
but production demo risk uses deliberate snapshots rather than merging those
marks with last-writer-wins semantics.

Themes (ROADMAP M10.1):
- Equity Vol — cash equity + options + index future (vol / skew book)
- Rates Macro — bonds, swaps, IR future (rates DV01 book)
- Cross-Asset — multi-asset macro book (default ``SAMPLE_PORTFOLIO``)

``SAMPLE_PORTFOLIO`` remains the Cross-Asset book with stable id ``global-macro``
so existing tests, DI defaults, and seeds stay compatible.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.models import MarketSnapshot, Portfolio
from app.market.vol_surfaces import VolSurface

DemoTheme = Literal["equity_vol", "rates_macro", "cross_asset"]


class DemoPortfolioSummary(BaseModel):
    """Catalog entry for demo books (list API / scripts; no risk numbers)."""

    id: str
    name: str
    theme: DemoTheme
    desk: str
    strategy: str
    position_count: int = Field(ge=0)
    description: str


EQUITY_VOL_PORTFOLIO = Portfolio.model_validate(
    {
        "id": "equity-vol",
        "name": "Equity Vol Demo",
        "firm": "RiskForge",
        "desk": "Equity Derivatives",
        "strategy": "Vol Trading",
        "positions": [
            {
                "type": "equity",
                "id": "eq-nvda",
                "symbol": "NVDA",
                "quantity": 800,
                "price": 118.50,
                "sector": "Technology",
            },
            {
                "type": "equity",
                "id": "eq-spy",
                "symbol": "SPY",
                "quantity": 600,
                "price": 565.00,
                "sector": "ETF",
            },
            {
                "type": "european_option",
                "id": "opt-spy-put",
                "symbol": "SPY",
                "quantity": 400,
                "spot": 565.00,
                "strike": 540.0,
                "maturity_years": 0.5,
                "volatility": 0.22,
                "risk_free_rate": 0.04,
                "option_type": "put",
                "sector": "ETF",
            },
            {
                "type": "european_option",
                "id": "opt-nvda-call",
                "symbol": "NVDA",
                "quantity": -250,
                "spot": 118.50,
                "strike": 130.0,
                "maturity_years": 0.35,
                "volatility": 0.46,
                "risk_free_rate": 0.04,
                "option_type": "call",
                "sector": "Technology",
            },
            {
                "type": "european_option",
                "id": "opt-spy-call-short",
                "symbol": "SPY",
                "quantity": -200,
                "spot": 565.00,
                "strike": 580.0,
                "maturity_years": 0.25,
                "volatility": 0.18,
                "risk_free_rate": 0.04,
                "option_type": "call",
                "sector": "ETF",
            },
            {
                "type": "equity_future",
                "id": "fut-es",
                "symbol": "SPY",
                "quantity": 15,
                "spot": 565.0,
                "multiplier": 50.0,
                "maturity_years": 0.25,
            },
        ],
    }
)

RATES_MACRO_PORTFOLIO = Portfolio.model_validate(
    {
        "id": "rates-macro",
        "name": "Rates Macro Demo",
        "firm": "RiskForge",
        "desk": "Rates",
        "strategy": "Macro Rates",
        "positions": [
            {
                "type": "bond",
                "id": "bond-ust2",
                "issuer": "UST 2Y",
                "face_value": 3_000_000,
                "quantity": 1,
                "maturity_years": 1.9,
                "yield_rate": 0.043,
                "duration": 1.85,
            },
            {
                "type": "bond",
                "id": "bond-ust10",
                "issuer": "UST 10Y",
                "face_value": 2_000_000,
                "quantity": 1,
                "maturity_years": 9.5,
                "yield_rate": 0.041,
                "duration": 7.8,
            },
            {
                "type": "swap",
                "id": "swap-usd2y",
                "currency": "USD",
                "notional": 8_000_000,
                "maturity_years": 2.0,
                "fixed_rate": 0.042,
                "market_swap_rate": 0.043,
                "pay_fixed": True,
                "duration": 1.9,
            },
            {
                "type": "swap",
                "id": "swap-usd5y",
                "currency": "USD",
                "notional": 5_000_000,
                "maturity_years": 5.0,
                "fixed_rate": 0.039,
                "market_swap_rate": 0.041,
                "pay_fixed": False,
                "duration": 4.3,
            },
            {
                "type": "swap",
                "id": "swap-usd10y",
                "currency": "USD",
                "notional": 3_000_000,
                "maturity_years": 10.0,
                "fixed_rate": 0.040,
                "market_swap_rate": 0.0415,
                "pay_fixed": True,
                "duration": 8.2,
            },
            {
                "type": "ir_future",
                "id": "fut-ed",
                "currency": "USD",
                "quantity": 40,
                "pv01": 25.0,
                "quoted_rate": 0.042,
                "forward_rate": 0.0425,
                "maturity_years": 0.25,
            },
        ],
    }
)

CROSS_ASSET_PORTFOLIO = Portfolio.model_validate(
    {
        "id": "global-macro",
        "name": "Global Macro Demo",
        "firm": "RiskForge",
        "desk": "Global Macro",
        "strategy": "Multi-Asset",
        "positions": [
            {
                "type": "equity",
                "id": "eq-nvda",
                "symbol": "NVDA",
                "quantity": 1200,
                "price": 118.50,
                "sector": "Technology",
            },
            {
                "type": "equity",
                "id": "eq-spy",
                "symbol": "SPY",
                "quantity": 900,
                "price": 565.00,
                "sector": "ETF",
            },
            {
                "type": "european_option",
                "id": "opt-spy-put",
                "symbol": "SPY",
                "quantity": 500,
                "spot": 565.00,
                "strike": 540.0,
                "maturity_years": 0.5,
                "volatility": 0.22,
                "risk_free_rate": 0.04,
                "option_type": "put",
                "sector": "ETF",
            },
            {
                "type": "european_option",
                "id": "opt-nvda-call",
                "symbol": "NVDA",
                "quantity": -350,
                "spot": 118.50,
                "strike": 130.0,
                "maturity_years": 0.35,
                "volatility": 0.46,
                "risk_free_rate": 0.04,
                "option_type": "call",
                "sector": "Technology",
            },
            {
                "type": "bond",
                "id": "bond-ust10",
                "issuer": "UST 10Y",
                "face_value": 2_000_000,
                "quantity": 1,
                "maturity_years": 9.5,
                "yield_rate": 0.041,
                "duration": 7.8,
            },
            {
                "type": "swap",
                "id": "swap-usd5y",
                "currency": "USD",
                "notional": 5_000_000,
                "maturity_years": 5.0,
                "fixed_rate": 0.039,
                "market_swap_rate": 0.041,
                "pay_fixed": True,
                "duration": 4.3,
            },
            {
                "type": "equity_future",
                "id": "fut-es",
                "symbol": "SPY",
                "quantity": 20,
                "spot": 565.0,
                "multiplier": 50.0,
                "maturity_years": 0.25,
            },
            {
                "type": "fx_forward",
                "id": "fxf-eurusd",
                "pair": "EURUSD",
                "notional_base": 1_000_000,
                "spot": 1.10,
                "strike": 1.105,
                "maturity_years": 0.5,
                "domestic_rate": 0.04,
                "foreign_rate": 0.03,
            },
            {
                "type": "fx_option",
                "id": "fxo-eurusd",
                "pair": "EURUSD",
                "notional_base": 250_000,
                "spot": 1.10,
                "strike": 1.12,
                "maturity_years": 0.4,
                "volatility": 0.12,
                "option_type": "call",
            },
        ],
    }
)

# Stable default for DI / tests / GET /portfolio.
SAMPLE_PORTFOLIO = CROSS_ASSET_PORTFOLIO

_DEMO_DESCRIPTIONS: dict[str, str] = {
    "equity-vol": (
        "Equity and listed-option book with index future hedge — "
        "illustrates equity spot and vol risk factors."
    ),
    "rates-macro": (
        "Treasury, IRS, and STIR-future book — "
        "illustrates rates DV01 / curve risk without equity or FX."
    ),
    "global-macro": (
        "Cross-asset multi-asset macro book (equity, vol, rates, FX) — "
        "default demo portfolio for the risk terminal (theme: cross_asset)."
    ),
}

_DEMO_THEMES: dict[str, DemoTheme] = {
    "equity-vol": "equity_vol",
    "rates-macro": "rates_macro",
    "global-macro": "cross_asset",
}

# Canonical ordered catalog (Equity Vol → Rates Macro → Cross-Asset).
DEMO_PORTFOLIOS: tuple[Portfolio, ...] = (
    EQUITY_VOL_PORTFOLIO,
    RATES_MACRO_PORTFOLIO,
    CROSS_ASSET_PORTFOLIO,
)

DEMO_PORTFOLIOS_BY_ID: dict[str, Portfolio] = {p.id: p for p in DEMO_PORTFOLIOS}


def _spy_demo_surface() -> dict:
    """SPY smile/term grid preserving the two equity-vol demo option marks."""
    return VolSurface.from_grid(
        "SPY",
        "equity",
        {
            ("3M", 0.9): 0.18,
            ("3M", 1.0): 0.18,
            ("3M", 1.1): 0.18,
            ("6M", 0.9): 0.22,
            ("6M", 1.0): 0.22,
            ("6M", 1.1): 0.22,
        },
    ).to_dict()


_DEMO_MARKETS: dict[str, MarketSnapshot] = {
    "equity-vol": MarketSnapshot(
        id="demo:equity-vol",
        equity_spots={"NVDA": 118.50, "SPY": 565.00},
        equity_vols={"NVDA": 0.46, "SPY": 0.22},
        rates={"USD": 0.04},
        dividend_yields={"NVDA": 0.0, "SPY": 0.0},
        vol_surfaces={"SPY": _spy_demo_surface()},
    ),
    "rates-macro": MarketSnapshot(
        id="demo:rates-macro",
        rates={"USD": 0.04},
        key_rates={
            "USD": {
                "0.25Y": 0.0425,
                "1.9Y": 0.043 * ((694.0 / 365.0) / 1.9),
                "2Y": 0.043,
                "5Y": 0.041,
                "9.5Y": 0.041 * ((3468.0 / 365.0) / 9.5),
                "10Y": 0.0415,
            }
        },
        projection_rates={"USD": 0.0425},
    ),
    "global-macro": MarketSnapshot(
        id="demo:global-macro",
        equity_spots={"NVDA": 118.50, "SPY": 565.00},
        equity_vols={"NVDA": 0.46, "SPY": 0.22},
        fx_spots={"EURUSD": 1.10},
        fx_vols={"EURUSD": 0.12},
        rates={"USD": 0.04, "EUR": 0.03},
        key_rates={
            "USD": {
                "5Y": 0.041,
                "9.5Y": 0.041 * ((3468.0 / 365.0) / 9.5),
            }
        },
        dividend_yields={"NVDA": 0.0, "SPY": 0.0},
    ),
}

_DEMO_AGGREGATE_MARKETS: dict[str, MarketSnapshot] = {
    "equity-vol": MarketSnapshot(
        id="demo-aggregate:equity-vol",
        equity_spots={"NVDA": 118.50, "SPY": 565.00},
        equity_vols={"NVDA": 0.46, "SPY": 0.18},
        rates={"USD": 0.04},
        dividend_yields={"NVDA": 0.0, "SPY": 0.0},
    ),
    "rates-macro": MarketSnapshot(
        id="demo-aggregate:rates-macro",
        rates={"USD": 0.0425},
    ),
    "global-macro": MarketSnapshot(
        id="demo-aggregate:global-macro",
        equity_spots={"NVDA": 118.50, "SPY": 565.00},
        equity_vols={"NVDA": 0.46, "SPY": 0.22},
        fx_spots={"EURUSD": 1.10},
        fx_vols={"EURUSD": 0.12},
        rates={"USD": 0.04, "EUR": 0.03},
        dividend_yields={"NVDA": 0.0, "SPY": 0.0},
    ),
}


def _matching_demo_id(portfolio: Portfolio) -> str | None:
    """Bind a canned snapshot only for exact demo identity (id and position ids)."""
    demo = DEMO_PORTFOLIOS_BY_ID.get(portfolio.id)
    if demo is None:
        return None
    position_ids = {position.id for position in portfolio.positions}
    demo_ids = {position.id for position in demo.positions}
    if position_ids == demo_ids:
        return portfolio.id
    return None


def demo_market_snapshot(portfolio: Portfolio) -> MarketSnapshot:
    """Resolve an explicit demo snapshot, otherwise validate legacy sample marks."""
    demo_id = _matching_demo_id(portfolio)
    if demo_id is not None:
        return _DEMO_MARKETS[demo_id]

    from app.market.demo_snapshot import DemoSampleMarksSnapshotAdapter

    return DemoSampleMarksSnapshotAdapter().snapshot(portfolio)


def demo_aggregate_market_snapshot(portfolio: Portfolio) -> MarketSnapshot:
    """Explicit compatibility snapshot for pre-R0.2 demo stress/attribution goldens."""
    demo_id = _matching_demo_id(portfolio)
    if demo_id is not None:
        return _DEMO_AGGREGATE_MARKETS[demo_id]
    return demo_market_snapshot(portfolio)


class DemoPortfolioMarketDataProvider:
    """Application-boundary resolver for explicit demos and validated ad-hoc books."""

    def snapshot(self, portfolio: Portfolio) -> MarketSnapshot:
        return demo_market_snapshot(portfolio)


class DemoAggregateMarketDataProvider:
    """Resolve deliberate aggregate snapshots for unchanged demo risk goldens."""

    def snapshot(self, portfolio: Portfolio) -> MarketSnapshot:
        return demo_aggregate_market_snapshot(portfolio)


def get_demo_portfolio(portfolio_id: str) -> Portfolio | None:
    """Return a themed demo portfolio by id, or None if unknown."""
    return DEMO_PORTFOLIOS_BY_ID.get(portfolio_id)


def demo_portfolio_summaries() -> list[DemoPortfolioSummary]:
    """Stable catalog summaries for list endpoints and scripts."""
    return [
        DemoPortfolioSummary(
            id=p.id,
            name=p.name,
            theme=_DEMO_THEMES[p.id],
            desk=p.desk,
            strategy=p.strategy,
            position_count=len(p.positions),
            description=_DEMO_DESCRIPTIONS[p.id],
        )
        for p in DEMO_PORTFOLIOS
    ]
