from app.domain.models import Portfolio

SAMPLE_PORTFOLIO = Portfolio.model_validate({
    "id": "global-macro",
    "name": "Global Macro Demo",
    "positions": [
        {"type": "equity", "id": "eq-nvda", "symbol": "NVDA", "quantity": 1200, "price": 118.50, "sector": "Technology"},
        {"type": "equity", "id": "eq-spy", "symbol": "SPY", "quantity": 900, "price": 565.00, "sector": "ETF"},
        {"type": "european_option", "id": "opt-spy-put", "symbol": "SPY", "quantity": 500, "spot": 565.00, "strike": 540.0, "maturity_years": 0.5, "volatility": 0.22, "risk_free_rate": 0.04, "option_type": "put", "sector": "ETF"},
        {"type": "european_option", "id": "opt-nvda-call", "symbol": "NVDA", "quantity": -350, "spot": 118.50, "strike": 130.0, "maturity_years": 0.35, "volatility": 0.46, "risk_free_rate": 0.04, "option_type": "call", "sector": "Technology"},
        {"type": "bond", "id": "bond-ust10", "issuer": "UST 10Y", "face_value": 2_000_000, "quantity": 1, "maturity_years": 9.5, "yield_rate": 0.041, "duration": 7.8},
        {"type": "swap", "id": "swap-usd5y", "currency": "USD", "notional": 5_000_000, "maturity_years": 5.0, "fixed_rate": 0.039, "market_swap_rate": 0.041, "pay_fixed": True, "duration": 4.3},
        {"type": "equity_future", "id": "fut-es", "symbol": "SPY", "quantity": 20, "spot": 565.0, "multiplier": 50.0, "maturity_years": 0.25},
        {"type": "fx_forward", "id": "fxf-eurusd", "pair": "EURUSD", "notional_base": 1_000_000, "spot": 1.10, "strike": 1.105, "maturity_years": 0.5, "domestic_rate": 0.04, "foreign_rate": 0.03},
        {"type": "fx_option", "id": "fxo-eurusd", "pair": "EURUSD", "notional_base": 250_000, "spot": 1.10, "strike": 1.12, "maturity_years": 0.4, "volatility": 0.12, "option_type": "call"},
    ],
})
