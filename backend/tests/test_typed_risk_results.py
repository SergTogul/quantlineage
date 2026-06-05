"""R0.9.2 / RF-010: RiskEngine.calculate returns typed RiskSummary, not a bare dict."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import get_type_hints

import pytest

from app.domain.models import EquityPosition, MarketSnapshot, Portfolio, RiskSummary, VaRMethodology
from app.interfaces.risk import RiskEngine
from app.pricing.builtin import BuiltinPricingEngine
from app.risk.historical import HistoricalRiskEngine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PRICING = BuiltinPricingEngine()
BOOK = Portfolio(
    id="typed-risk",
    name="typed-risk",
    positions=[EquityPosition(type="equity", id="unit", symbol="UNIT", quantity=1.0)],
)
UNIT_MARKET = MarketSnapshot(id="typed-unit", equity_spots={"UNIT": 1.0}, rates={"USD": 0.04})

RESULT_FIELDS = (
    "portfolio_id",
    "market_value",
    "delta",
    "gamma",
    "vega",
    "dv01",
    "fx_delta",
    "var_95",
    "var_99",
    "expected_shortfall_99",
    "methodology",
)


def test_risk_engine_abc_calculate_returns_risk_summary() -> None:
    hints = get_type_hints(RiskEngine.calculate)
    assert hints["return"] is RiskSummary, f"ABC calculate return is {hints.get('return')!r}"


def test_historical_engine_calculate_is_risk_summary_not_dict() -> None:
    result = HistoricalRiskEngine(seed=1, observations=8).calculate(
        BOOK, PRICING, market=UNIT_MARKET
    )
    assert isinstance(result, RiskSummary)
    assert not isinstance(result, dict)
    assert result.portfolio_id == BOOK.id
    assert result.market_value == pytest.approx(1.0)
    assert result.methodology is VaRMethodology.DELTA_GAMMA
    for name in RESULT_FIELDS:
        assert hasattr(result, name), name


def test_app_risk_and_domain_do_not_import_fastapi() -> None:
    offenders: list[str] = []
    for package in ("risk", "domain"):
        root = BACKEND_ROOT / "app" / package
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                for module in modules:
                    if module == "fastapi" or module.startswith("fastapi."):
                        offenders.append(f"{package}/{path.relative_to(root)}:{module}")
    assert not offenders, f"risk/domain must not import FastAPI: {offenders}"
