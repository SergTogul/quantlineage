"""In-code demo portfolios and their explicit market snapshots.

No live market-data vendor feeds. Demo positions carry contractual economics only; live marks live
exclusively in ``_DEMO_MARKETS`` / ``_DEMO_AGGREGATE_MARKETS``
(and explicit test snapshots).

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
from app.market.curves import CurveNode, YieldCurve, tenor_to_years
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
        "firm": "QuantLineage",
        "desk": "Equity Derivatives",
        "strategy": "Vol Trading",
        "positions": [
            {
                "type": "equity",
                "id": "eq-nvda",
                "symbol": "NVDA",
                "quantity": 800,
                "sector": "Technology",
            },
            {
                "type": "equity",
                "id": "eq-aapl",
                "symbol": "AAPL",
                "quantity": 500,
                "sector": "Technology",
            },
            {
                "type": "equity",
                "id": "eq-msft",
                "symbol": "MSFT",
                "quantity": 400,
                "sector": "Technology",
            },
            {
                "type": "equity",
                "id": "eq-spy",
                "symbol": "SPY",
                "quantity": 600,
                "sector": "ETF",
            },
            {
                "type": "european_option",
                "id": "opt-spy-put",
                "symbol": "SPY",
                "quantity": 400,
                "strike": 540.0,
                "maturity_years": 0.5,
                "option_type": "put",
                "sector": "ETF",
            },
            {
                "type": "european_option",
                "id": "opt-nvda-call",
                "symbol": "NVDA",
                "quantity": -250,
                "strike": 130.0,
                "maturity_years": 0.35,
                "option_type": "call",
                "sector": "Technology",
            },
            {
                "type": "european_option",
                "id": "opt-aapl-call",
                "symbol": "AAPL",
                "quantity": -150,
                "strike": 190.0,
                "maturity_years": 0.4,
                "option_type": "call",
                "sector": "Technology",
            },
            {
                "type": "european_option",
                "id": "opt-spy-call-short",
                "symbol": "SPY",
                "quantity": -200,
                "strike": 580.0,
                "maturity_years": 0.25,
                "option_type": "call",
                "sector": "ETF",
            },
            {
                "type": "equity_future",
                "id": "fut-es",
                "symbol": "SPY",
                "quantity": 15,
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
        "firm": "QuantLineage",
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
                "duration": 1.85,
            },
            {
                "type": "bond",
                "id": "bond-ust10",
                "issuer": "UST 10Y",
                "face_value": 2_000_000,
                "quantity": 1,
                "maturity_years": 9.5,
                "duration": 7.8,
            },
            {
                "type": "swap",
                "id": "swap-usd2y",
                "currency": "USD",
                "notional": 8_000_000,
                "maturity_years": 2.0,
                "fixed_rate": 0.042,
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
                "pay_fixed": True,
                "duration": 8.2,
            },
            {
                "type": "ir_future",
                "id": "fut-ed",
                "currency": "USD",
                "quantity": 40,
                "pv01": 25.0,
                "maturity_years": 0.25,
            },
        ],
    }
)

CROSS_ASSET_PORTFOLIO = Portfolio.model_validate(
    {
        "id": "global-macro",
        "name": "Global Macro Demo",
        "firm": "QuantLineage",
        "desk": "Global Macro",
        "strategy": "Multi-Asset",
        "positions": [
            {
                "type": "equity",
                "id": "eq-nvda",
                "symbol": "NVDA",
                "quantity": 1200,
                "sector": "Technology",
            },
            {
                "type": "equity",
                "id": "eq-aapl",
                "symbol": "AAPL",
                "quantity": 700,
                "sector": "Technology",
            },
            {
                "type": "equity",
                "id": "eq-msft",
                "symbol": "MSFT",
                "quantity": 600,
                "sector": "Technology",
            },
            {
                "type": "equity",
                "id": "eq-spy",
                "symbol": "SPY",
                "quantity": 900,
                "sector": "ETF",
            },
            {
                "type": "european_option",
                "id": "opt-spy-put",
                "symbol": "SPY",
                "quantity": 500,
                "strike": 540.0,
                "maturity_years": 0.5,
                "option_type": "put",
                "sector": "ETF",
            },
            {
                "type": "european_option",
                "id": "opt-nvda-call",
                "symbol": "NVDA",
                "quantity": -350,
                "strike": 130.0,
                "maturity_years": 0.35,
                "option_type": "call",
                "sector": "Technology",
            },
            {
                "type": "european_option",
                "id": "opt-msft-put",
                "symbol": "MSFT",
                "quantity": 200,
                "strike": 400.0,
                "maturity_years": 0.45,
                "option_type": "put",
                "sector": "Technology",
            },
            {
                "type": "bond",
                "id": "bond-ust10",
                "issuer": "UST 10Y",
                "face_value": 2_000_000,
                "quantity": 1,
                "maturity_years": 9.5,
                "duration": 7.8,
            },
            {
                "type": "swap",
                "id": "swap-usd5y",
                "currency": "USD",
                "notional": 5_000_000,
                "maturity_years": 5.0,
                "fixed_rate": 0.039,
                "pay_fixed": True,
                "duration": 4.3,
            },
            {
                "type": "equity_future",
                "id": "fut-es",
                "symbol": "SPY",
                "quantity": 20,
                "multiplier": 50.0,
                "maturity_years": 0.25,
            },
            {
                "type": "fx_forward",
                "id": "fxf-eurusd",
                "pair": "EURUSD",
                "notional_base": 1_000_000,
                "strike": 1.105,
                "maturity_years": 0.5,
            },
            {
                "type": "fx_option",
                "id": "fxo-eurusd",
                "pair": "EURUSD",
                "notional_base": 250_000,
                "strike": 1.12,
                "maturity_years": 0.4,
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
        "illustrates per-name equity spot and vol risk (AAPL/MSFT/NVDA/SPY)."
    ),
    "rates-macro": (
        "Treasury, IRS, and STIR-future book — "
        "illustrates rates DV01 / key-rate DV01 on demo SOFR/OIS-style zeros "
        "(not a production multi-curve framework)."
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


# Production HistoricalFactorPanel (DEFAULT_PRODUCTION_PANEL_FACTORS) shocks every
# RateZero column via MarketSnapshot.apply on FULL_REVALUATION. Demo key_rates
# must include USD 0Y/2Y/5Y/10Y or panel apply fail-closes (HTTP 500 on /risk/es).
# Equity/FX names on the per-factor panel must likewise exist on every demo
# snapshot so FULL_REVALUATION does not KeyError a missing mark.
_PANEL_USD_KEY_RATES: dict[str, float] = {
    "0Y": 0.04,
    "2Y": 0.043,
    "5Y": 0.041,
    "10Y": 0.0415,
}

_RATES_MACRO_USD_KEY_RATES: dict[str, float] = {
    **_PANEL_USD_KEY_RATES,
    "0.25Y": 0.0425,
    "1.9Y": 0.043 * ((694.0 / 365.0) / 1.9),
    "9.5Y": 0.041 * ((3468.0 / 365.0) / 9.5),
}

_RATES_CURVE_LIMITATIONS = (
    "Demo SOFR/OIS-style zeros; not a production multi-curve framework."
)


def _usd_curve_payload(
    name: str,
    curve_type: Literal["discount", "projection"],
    zeros: dict[str, float],
) -> dict:
    """Named snapshot curve payload. Extra keys are display-only limitations."""
    nodes = tuple(
        CurveNode(tenor=tenor, years=tenor_to_years(tenor), zero_rate=float(rate))
        for tenor, rate in sorted(zeros.items(), key=lambda item: tenor_to_years(item[0]))
    )
    payload = YieldCurve(
        currency="USD",
        curve_type=curve_type,
        name=name,
        nodes=nodes,
    ).to_dict()
    payload["limitations"] = _RATES_CURVE_LIMITATIONS
    return payload


def _rates_macro_curves() -> dict[str, dict]:
    """Deterministic USD OIS discount + SOFR-style projection for the rates demo.

    2Y/5Y/10Y are the showcase nodes. Extra OIS pillars keep bond maturities on
    the same zeros as the existing key_rates map. This is not dual-curve
    production calibration.
    """
    ois_zeros = {
        tenor: rate
        for tenor, rate in _RATES_MACRO_USD_KEY_RATES.items()
        if tenor != "0Y"
    }
    sofr_zeros = {tenor: 0.0425 for tenor in ("2Y", "5Y", "10Y")}
    return {
        "USD_OIS": _usd_curve_payload("USD_OIS", "discount", ois_zeros),
        "USD_SOFR": _usd_curve_payload("USD_SOFR", "projection", sofr_zeros),
    }

_PANEL_EQUITY_SPOTS: dict[str, float] = {
    "AAPL": 185.00,
    "MSFT": 415.00,
    "NVDA": 118.50,
    "SPY": 565.00,
}
_PANEL_EQUITY_VOLS: dict[str, float] = {
    "AAPL": 0.28,
    "MSFT": 0.24,
    "NVDA": 0.46,
    "SPY": 0.22,
}
_PANEL_DIVIDEND_YIELDS: dict[str, float] = {symbol: 0.0 for symbol in _PANEL_EQUITY_SPOTS}
_PANEL_FX_SPOTS: dict[str, float] = {"EURUSD": 1.10}
_PANEL_FX_VOLS: dict[str, float] = {"EURUSD": 0.12}

_DEMO_MARKETS: dict[str, MarketSnapshot] = {
    "equity-vol": MarketSnapshot(
        id="demo:equity-vol",
        equity_spots=dict(_PANEL_EQUITY_SPOTS),
        equity_vols=dict(_PANEL_EQUITY_VOLS),
        fx_spots=dict(_PANEL_FX_SPOTS),
        fx_vols=dict(_PANEL_FX_VOLS),
        rates={"USD": 0.04},
        key_rates={"USD": dict(_PANEL_USD_KEY_RATES)},
        dividend_yields=dict(_PANEL_DIVIDEND_YIELDS),
        vol_surfaces={"SPY": _spy_demo_surface()},
    ),
    "rates-macro": MarketSnapshot(
        id="demo:rates-macro",
        equity_spots=dict(_PANEL_EQUITY_SPOTS),
        equity_vols=dict(_PANEL_EQUITY_VOLS),
        fx_spots=dict(_PANEL_FX_SPOTS),
        fx_vols=dict(_PANEL_FX_VOLS),
        rates={"USD": 0.04},
        key_rates={"USD": dict(_RATES_MACRO_USD_KEY_RATES)},
        dividend_yields=dict(_PANEL_DIVIDEND_YIELDS),
        projection_rates={"USD": 0.0425},
        ir_future_quotes={"USD": 0.042},
        curves=_rates_macro_curves(),
    ),
    "global-macro": MarketSnapshot(
        id="demo:global-macro",
        equity_spots=dict(_PANEL_EQUITY_SPOTS),
        equity_vols=dict(_PANEL_EQUITY_VOLS),
        fx_spots=dict(_PANEL_FX_SPOTS),
        fx_vols=dict(_PANEL_FX_VOLS),
        rates={"USD": 0.04, "EUR": 0.03},
        key_rates={
            "USD": {
                **_PANEL_USD_KEY_RATES,
                "9.5Y": 0.041 * ((3468.0 / 365.0) / 9.5),
            }
        },
        dividend_yields=dict(_PANEL_DIVIDEND_YIELDS),
    ),
}

_DEMO_AGGREGATE_MARKETS: dict[str, MarketSnapshot] = {
    "equity-vol": MarketSnapshot(
        id="demo-aggregate:equity-vol",
        equity_spots=dict(_PANEL_EQUITY_SPOTS),
        equity_vols={**_PANEL_EQUITY_VOLS, "SPY": 0.18},
        fx_spots=dict(_PANEL_FX_SPOTS),
        fx_vols=dict(_PANEL_FX_VOLS),
        rates={"USD": 0.04},
        dividend_yields=dict(_PANEL_DIVIDEND_YIELDS),
    ),
    "rates-macro": MarketSnapshot(
        id="demo-aggregate:rates-macro",
        equity_spots=dict(_PANEL_EQUITY_SPOTS),
        equity_vols=dict(_PANEL_EQUITY_VOLS),
        fx_spots=dict(_PANEL_FX_SPOTS),
        fx_vols=dict(_PANEL_FX_VOLS),
        rates={"USD": 0.0425},
        dividend_yields=dict(_PANEL_DIVIDEND_YIELDS),
        ir_future_quotes={"USD": 0.042},
    ),
    "global-macro": MarketSnapshot(
        id="demo-aggregate:global-macro",
        equity_spots=dict(_PANEL_EQUITY_SPOTS),
        equity_vols=dict(_PANEL_EQUITY_VOLS),
        fx_spots=dict(_PANEL_FX_SPOTS),
        fx_vols=dict(_PANEL_FX_VOLS),
        rates={"USD": 0.04, "EUR": 0.03},
        dividend_yields=dict(_PANEL_DIVIDEND_YIELDS),
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
    """Resolve a canned demo snapshot; ad-hoc books must supply their own market."""
    demo_id = _matching_demo_id(portfolio)
    if demo_id is not None:
        return _DEMO_MARKETS[demo_id]

    from app.market.demo_snapshot import SampleMarksRemovedError

    raise SampleMarksRemovedError(
        "sample marks no longer live on Position DTOs; "
        "supply an explicit MarketSnapshot (or use a canned demo portfolio id)"
    )


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
