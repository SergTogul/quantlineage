"""Stress / reverse-stress / threat routes (M7.1). Under /risk until M7.2.

R0.4.2-D/E: Primary UI/custom POST path is formal ``ScenarioWire`` under
``/risk/stress/formal/*`` (custom, evaluate/custom, compare). Legacy
``StressScenario`` POST bodies on ``/stress/custom``, ``/evaluate/custom``,
``/compare`` are **deprecated** back-compat only and are adapted to canonical
``Scenario`` at this HTTP layer. List wire remains formal
(``GET /scenarios``; ``/scenarios/formal`` identical alias).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends

from app.api.backpressure import reject_inline_heavy
from app.api.deps import (
    get_baseline_stress_scenarios,
    get_default_stress_scenarios,
    get_portfolio_service,
)
from app.api.openapi_examples import (
    FORMAL_CUSTOM_STRESS_BODY_EXAMPLES,
    FORMAL_HEDGE_COMPARE_BODY_EXAMPLES,
    HEDGE_COMPARE_BODY_EXAMPLES,
    RESP_HEDGE_COMPARE,
    RESP_REVERSE,
    RESP_REVERSE_MULTI,
    RESP_STRESS,
    REVERSE_BODY_EXAMPLES,
    REVERSE_MULTI_BODY_EXAMPLES,
    STRESS_BODY_EXAMPLES,
)
from app.api.scenario_wire import (
    FormalCustomStressRequest,
    FormalScenarioComparisonRequest,
    ScenarioWire,
    scenario_to_wire,
    stresses_to_scenarios,
    wires_to_scenarios,
)
from app.api.schemas import (
    CustomStressRequest,
    MultiFactorReverseStressRequest,
    ReverseStressRequest,
    ScenarioComparisonRequest,
)
from app.domain.models import (
    HedgeComparisonReport,
    MultiFactorReverseStressResult,
    Portfolio,
    ReverseStressResult,
    StressResult,
    StressScenario,
)
from app.risk.scenario_model import Scenario
from app.services.portfolio_service import PortfolioService

router = APIRouter(prefix="/risk", tags=["stress"])


def _formal_scenario_wires(scenarios: list[Scenario]) -> list[ScenarioWire]:
    """Project DI canonical Scenario definitions onto the formal list wire."""
    return [scenario_to_wire(s) for s in scenarios]


def _canonical_from_legacy(
    portfolio: Portfolio,
    scenarios: list[StressScenario],
    service: PortfolioService,
):
    """Adapt deprecated StressScenario POST bodies to engine-facing Scenario."""
    return stresses_to_scenarios(scenarios, service.market_snapshot(portfolio))


@router.post(
    "/stress",
    response_model=list[StressResult],
    summary="Baseline stress P&L",
    responses=RESP_STRESS,
)
def risk_stress(
    portfolio: Annotated[
        Portfolio,
        Body(openapi_examples=STRESS_BODY_EXAMPLES),
    ],
    scenarios: list[Scenario] = Depends(get_baseline_stress_scenarios),
    service: PortfolioService = Depends(get_portfolio_service),
) -> list[StressResult]:
    """Baseline stress P&L over DI DEFAULT scenarios (M5.9 follow-up)."""
    reject_inline_heavy(route="POST /risk/stress")
    return service.stresses(portfolio, scenarios)


@router.get(
    "/stress/scenarios",
    response_model=list[ScenarioWire],
    summary="List scenario definitions (formal Scenario wire)",
    description=(
        "R0.4.2-C **breaking change**: returns formal ``ScenarioWire`` "
        "(``category``, ``shocks[]``) instead of legacy ``StressScenario`` "
        "dicts (``equity_shock``, ``rates_shift_bps``, …). "
        "Same payload as ``GET /risk/stress/scenarios/formal``."
    ),
)
def risk_stress_scenarios(
    scenarios: list[Scenario] = Depends(get_default_stress_scenarios),
) -> list[ScenarioWire]:
    """List DI scenario definitions as formal wire; THREAT templates if repo empty."""
    return _formal_scenario_wires(scenarios)


@router.get(
    "/stress/scenarios/formal",
    response_model=list[ScenarioWire],
    summary="Alias: list scenarios as formal Scenario wire",
    description=(
        "Identical JSON to ``GET /risk/stress/scenarios`` (R0.4.2-C). "
        "Kept so clients that already call ``/formal`` keep working."
    ),
    deprecated=False,
)
def risk_stress_scenarios_formal(
    scenarios: list[Scenario] = Depends(get_default_stress_scenarios),
) -> list[ScenarioWire]:
    """Alias of ``GET /stress/scenarios`` — same formal wire payload."""
    return _formal_scenario_wires(scenarios)


@router.post(
    "/stress/custom",
    deprecated=True,
    summary="Custom stress P&L (legacy StressScenario — deprecated)",
    description=(
        "Deprecated R0.4.2-D: prefer ``POST /risk/stress/formal/custom`` with "
        "``ScenarioWire``. Retained for back-compat only."
    ),
)
def risk_stress_custom(
    request: CustomStressRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    reject_inline_heavy(route="POST /risk/stress/custom")
    return service.stresses(
        request.portfolio,
        _canonical_from_legacy(request.portfolio, request.scenarios, service),
    )


@router.post(
    "/stress/formal/custom",
    response_model=list[StressResult],
    summary="Custom stress P&L (formal Scenario wire)",
    responses=RESP_STRESS,
)
def risk_stress_formal_custom(
    request: Annotated[
        FormalCustomStressRequest,
        Body(openapi_examples=FORMAL_CUSTOM_STRESS_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
) -> list[StressResult]:
    """Accept formal Scenario wire; apply via StressEngine without StressScenario collapse."""
    reject_inline_heavy(route="POST /risk/stress/formal/custom")
    return service.stresses(request.portfolio, wires_to_scenarios(request.scenarios))


@router.post("/stress/evaluate")
def risk_stress_evaluate(
    portfolio: Portfolio,
    scenarios: list[Scenario] = Depends(get_default_stress_scenarios),
    service: PortfolioService = Depends(get_portfolio_service),
):
    """Threat evaluation over DI-backed scenario defaults (M5.9)."""
    reject_inline_heavy(route="POST /risk/stress/evaluate")
    return service.threat_evaluation(portfolio, scenarios)


@router.post(
    "/stress/evaluate/custom",
    deprecated=True,
    summary="Threat evaluation (legacy StressScenario — deprecated)",
    description=(
        "Deprecated R0.4.2-D: prefer ``POST /risk/stress/formal/evaluate/custom`` "
        "with ``ScenarioWire``. Retained for back-compat only."
    ),
)
def risk_stress_evaluate_custom(
    request: CustomStressRequest,
    service: PortfolioService = Depends(get_portfolio_service),
):
    reject_inline_heavy(route="POST /risk/stress/evaluate/custom")
    return service.threat_evaluation(
        request.portfolio,
        _canonical_from_legacy(request.portfolio, request.scenarios, service),
    )


@router.post(
    "/stress/formal/evaluate/custom",
    summary="Threat evaluation (formal Scenario wire)",
)
def risk_stress_formal_evaluate_custom(
    request: Annotated[
        FormalCustomStressRequest,
        Body(openapi_examples=FORMAL_CUSTOM_STRESS_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
):
    """Accept formal Scenario wire; evaluate via StressEngine without StressScenario collapse."""
    reject_inline_heavy(route="POST /risk/stress/formal/evaluate/custom")
    return service.threat_evaluation(
        request.portfolio, wires_to_scenarios(request.scenarios)
    )


@router.post(
    "/stress/reverse",
    response_model=ReverseStressResult,
    summary="Single-factor reverse stress",
    responses=RESP_REVERSE,
)
def risk_stress_reverse(
    request: Annotated[
        ReverseStressRequest,
        Body(openapi_examples=REVERSE_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
) -> ReverseStressResult:
    reject_inline_heavy(route="POST /risk/stress/reverse")
    return service.reverse_stress(
        request.portfolio,
        request.target_loss_pct,
        request.factor,
        request.max_shock,
    )


@router.post(
    "/stress/reverse/multi",
    response_model=MultiFactorReverseStressResult,
    summary="Multi-factor reverse stress",
    responses=RESP_REVERSE_MULTI,
)
def risk_stress_reverse_multi(
    request: Annotated[
        MultiFactorReverseStressRequest,
        Body(openapi_examples=REVERSE_MULTI_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
) -> MultiFactorReverseStressResult:
    reject_inline_heavy(route="POST /risk/stress/reverse/multi")
    return service.reverse_stress_multi(
        request.portfolio,
        request.target_loss_pct,
        factors=request.factors,
        weights=request.weights,
        max_shock=request.max_shock,
        max_shocks=request.max_shocks,
    )


@router.post(
    "/stress/compare",
    response_model=HedgeComparisonReport,
    deprecated=True,
    summary="Hedge comparison (legacy StressScenario — deprecated)",
    description=(
        "Deprecated R0.4.2-D: prefer ``POST /risk/stress/formal/compare`` with "
        "``ScenarioWire``. Retained for back-compat only."
    ),
    responses=RESP_HEDGE_COMPARE,
)
def risk_stress_compare(
    request: Annotated[
        ScenarioComparisonRequest,
        Body(openapi_examples=HEDGE_COMPARE_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
) -> HedgeComparisonReport:
    reject_inline_heavy(route="POST /risk/stress/compare")
    return service.compare_scenarios(
        request.portfolio,
        request.hedged_portfolio,
        _canonical_from_legacy(request.portfolio, request.scenarios, service),
        methodology=request.methodology,
    )


@router.post(
    "/stress/formal/compare",
    response_model=HedgeComparisonReport,
    summary="Hedge comparison (formal Scenario wire)",
    responses=RESP_HEDGE_COMPARE,
)
def risk_stress_formal_compare(
    request: Annotated[
        FormalScenarioComparisonRequest,
        Body(openapi_examples=FORMAL_HEDGE_COMPARE_BODY_EXAMPLES),
    ],
    service: PortfolioService = Depends(get_portfolio_service),
) -> HedgeComparisonReport:
    """Accept formal Scenario wire; compare via ScenarioComparisonEngine."""
    reject_inline_heavy(route="POST /risk/stress/formal/compare")
    return service.compare_scenarios(
        request.portfolio,
        request.hedged_portfolio,
        wires_to_scenarios(request.scenarios),
        methodology=request.methodology,
    )
