"""OpenAPI request/response/error examples for critical risk endpoints (M7.4).

Numbers are **illustrative only** — they document wire shapes for Swagger/ReDoc
and must not be treated as engine output or golden risk values.
"""

from __future__ import annotations

from typing import Any

from app.api.errors import ErrorBody

# Shared label for example payloads (docs only).
_ILLUSTRATIVE = (
    "Illustrative OpenAPI example only — numbers are not live engine output."
)

# Compact demo book reused across request examples (valid Portfolio shape).
EXAMPLE_PORTFOLIO: dict[str, Any] = {
    "id": "demo-book",
    "name": "Demo Book",
    "firm": "QuantLineage",
    "desk": "Global Macro",
    "strategy": "Multi-Asset",
    "positions": [
        {
            "type": "equity",
            "id": "eq-spy",
            "symbol": "SPY",
            "quantity": 100.0,
            "price": 565.0,
            "sector": "ETF",
            "book": "Equity",
        },
        {
            "type": "european_option",
            "id": "opt-spy-put",
            "symbol": "SPY",
            "quantity": 50.0,
            "spot": 565.0,
            "strike": 540.0,
            "maturity_years": 0.5,
            "volatility": 0.22,
            "risk_free_rate": 0.04,
            "option_type": "put",
            "sector": "ETF",
            "book": "Equity Derivatives",
        },
    ],
}

EXAMPLE_HEDGED_PORTFOLIO: dict[str, Any] = {
    **EXAMPLE_PORTFOLIO,
    "id": "demo-book-hedged",
    "name": "Demo Book (hedged)",
    "positions": [
        {
            **EXAMPLE_PORTFOLIO["positions"][0],
            "quantity": 40.0,
        },
        EXAMPLE_PORTFOLIO["positions"][1],
    ],
}

EXAMPLE_CRASH_SCENARIO: dict[str, Any] = {
    "name": "Equity crash −20%",
    "description": "Illustrative equity sell-off",
    "kind": "factor",
    "equity_shock": -0.20,
    "vol_shock": 0.40,
    "rates_shift_bps": 0.0,
    "fx_shock": 0.0,
}


def _ex(summary: str, value: Any, *, description: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"summary": summary, "value": value}
    if description is not None:
        item["description"] = description
    else:
        item["description"] = _ILLUSTRATIVE
    return item


def json_content_examples(examples: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build ``content.application/json.examples`` for a response or media type."""
    return {"application/json": {"examples": examples}}


def success_response(
    description: str,
    examples: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "description": description,
        "content": json_content_examples(examples),
    }


def error_response(
    description: str,
    examples: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "model": ErrorBody,
        "description": description,
        "content": json_content_examples(examples),
    }


# --- Error envelopes (M7.5 shape) -------------------------------------------------

EXAMPLE_VALIDATION_ERROR: dict[str, Any] = {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": {
        "errors": [
            {
                "type": "missing",
                "loc": ["body", "portfolio"],
                "msg": "Field required",
                "input": {},
            }
        ]
    },
}

EXAMPLE_BAD_REQUEST: dict[str, Any] = {
    "code": "bad_request",
    "message": "Invalid request",
    # OpenAPI generators omit JSON nulls; use empty object so ``details`` stays visible.
    "details": {},
}

EXAMPLE_NOT_FOUND: dict[str, Any] = {
    "code": "not_found",
    "message": "risk run not found: a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "details": {},
}

RESP_422 = error_response(
    "Validation error (`{code,message,details}`)",
    {"validation_error": _ex("Request validation failed", EXAMPLE_VALIDATION_ERROR)},
)

RESP_400 = error_response(
    "Bad request (`{code,message,details}`)",
    {"bad_request": _ex("Client error", EXAMPLE_BAD_REQUEST)},
)

RESP_404 = error_response(
    "Not found (`{code,message,details}`)",
    {"not_found": _ex("Missing resource", EXAMPLE_NOT_FOUND)},
)


# --- VaR / ES --------------------------------------------------------------------

PORTFOLIO_BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "demo_book": _ex("Demo multi-asset book (compact)", EXAMPLE_PORTFOLIO),
}

EXAMPLE_VAR_RESPONSE: dict[str, Any] = {
    "portfolio_id": "demo-book",
    "methodology": "DELTA_GAMMA",
    "methods": [
        {
            "method": "historical",
            "confidence": 0.99,
            "var": 12500.0,
            "expected_shortfall": 18200.0,
        },
        {
            "method": "parametric",
            "confidence": 0.99,
            "var": 11800.0,
            "expected_shortfall": 17100.0,
        },
    ],
    "contributions": [
        {
            "position_id": "eq-spy",
            "component_var": 9200.0,
            "contribution_pct": 78.0,
            "component_es": 14100.0,
            "es_contribution_pct": 77.5,
            "marginal_var": 9200.0,
        },
        {
            "position_id": "opt-spy-put",
            "component_var": 2600.0,
            "contribution_pct": 22.0,
            "component_es": 4100.0,
            "es_contribution_pct": 22.5,
            "marginal_var": 2600.0,
        },
    ],
}

EXAMPLE_ES_RESPONSE: dict[str, Any] = {
    "portfolio_id": "demo-book",
    "methodology": "DELTA_GAMMA",
    "confidence": 0.99,
    "portfolio_var": 12500.0,
    "portfolio_es": 18200.0,
    "by_position": [
        {
            "key": "eq-spy",
            "label": "eq-spy",
            "component_es": 14100.0,
            "contribution_pct": 77.5,
        }
    ],
    "by_book": [
        {
            "key": "Equity",
            "label": "Equity",
            "component_es": 14100.0,
            "contribution_pct": 77.5,
        }
    ],
    "by_strategy": [
        {
            "key": "Multi-Asset",
            "label": "Multi-Asset",
            "component_es": 18200.0,
            "contribution_pct": 100.0,
        }
    ],
    "by_desk": [
        {
            "key": "Global Macro",
            "label": "Global Macro",
            "component_es": 18200.0,
            "contribution_pct": 100.0,
        }
    ],
    "by_risk_factor": [
        {
            "key": "equity",
            "label": "Equity",
            "component_es": 15000.0,
            "contribution_pct": 82.4,
        }
    ],
    "reconciliation_error_position": 0.0,
    "reconciliation_error_book": 0.0,
    "reconciliation_error_strategy": 0.0,
    "reconciliation_error_desk": 0.0,
    "reconciliation_error_risk_factor": 0.0,
}

RESP_VAR = {
    200: success_response(
        "VaR report with historical/parametric methods and contributions",
        {"illustrative": _ex("Illustrative VaR report", EXAMPLE_VAR_RESPONSE)},
    ),
    422: RESP_422,
}

RESP_ES = {
    200: success_response(
        "Expected Shortfall contributions by position / book / desk / strategy / factor",
        {"illustrative": _ex("Illustrative ES contribution report", EXAMPLE_ES_RESPONSE)},
    ),
    422: RESP_422,
}


# --- What-if ---------------------------------------------------------------------

EXAMPLE_WHAT_IF_REQUEST: dict[str, Any] = {
    "portfolio": EXAMPLE_PORTFOLIO,
    "methodology": "DELTA_GAMMA",
    "changes": [
        {
            "operation": "add",
            "position": {
                "type": "equity",
                "id": "eq-whatif",
                "symbol": "SPY",
                "quantity": 50.0,
                "price": 565.0,
                "sector": "ETF",
                "book": "Equity",
            },
        }
    ],
}

EXAMPLE_WHAT_IF_RESPONSE: dict[str, Any] = {
    "portfolio_id": "demo-book",
    "methodology": "DELTA_GAMMA",
    "before": {
        "portfolio_id": "demo-book",
        "market_value": 62000.0,
        "delta": 95.0,
        "gamma": 0.12,
        "vega": 850.0,
        "dv01": 0.0,
        "fx_delta": 0.0,
        "var_95": 9800.0,
        "var_99": 12500.0,
        "expected_shortfall_99": 18200.0,
        "methodology": "DELTA_GAMMA",
    },
    "after": {
        "portfolio_id": "demo-book",
        "market_value": 90250.0,
        "delta": 145.0,
        "gamma": 0.12,
        "vega": 850.0,
        "dv01": 0.0,
        "fx_delta": 0.0,
        "var_95": 14200.0,
        "var_99": 18100.0,
        "expected_shortfall_99": 26400.0,
        "methodology": "DELTA_GAMMA",
    },
    "incremental": {
        "market_value": 28250.0,
        "delta": 50.0,
        "gamma": 0.0,
        "vega": 0.0,
        "dv01": 0.0,
        "fx_delta": 0.0,
        "var_95": 4400.0,
        "var_99": 5600.0,
        "expected_shortfall_99": 8200.0,
    },
    "changed_factor_exposures": [
        {
            "factor": "SPY",
            "factor_type": "equity",
            "bucket": "spot",
            "before": 56500.0,
            "after": 84750.0,
            "delta": 28250.0,
        }
    ],
    "changed_stress_losses": [
        {
            "scenario": "Equity crash −20%",
            "before_pnl": -8500.0,
            "after_pnl": -12800.0,
            "delta_pnl": -4300.0,
        }
    ],
}

WHAT_IF_BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "add_equity": _ex("Add equity position (hypothetical)", EXAMPLE_WHAT_IF_REQUEST),
}

RESP_WHAT_IF = {
    200: success_response(
        "Before/after risk and incremental deltas",
        {"illustrative": _ex("Illustrative what-if report", EXAMPLE_WHAT_IF_RESPONSE)},
    ),
    400: RESP_400,
    422: RESP_422,
}


# --- Stress / reverse / multi / hedge-compare ------------------------------------

EXAMPLE_STRESS_RESPONSE: list[dict[str, Any]] = [
    {
        "scenario": "Equity crash −20%",
        "pnl": -8500.0,
        "by_position": {"eq-spy": -11300.0, "opt-spy-put": 2800.0},
    }
]

EXAMPLE_REVERSE_REQUEST: dict[str, Any] = {
    "portfolio": EXAMPLE_PORTFOLIO,
    "target_loss_pct": 0.05,
    "factor": "equity",
    "max_shock": 0.80,
}

EXAMPLE_REVERSE_RESPONSE: dict[str, Any] = {
    "factor": "equity",
    "target_loss_pct": 0.05,
    "required_shock": -0.18,
    "achieved_loss_pct": 0.05,
    "converged": True,
    "target_loss": 3100.0,
    "pnl": -3100.0,
    "shock_unit": "relative",
    "base_market_value": 62000.0,
    "convergence": {
        "iterations": 12,
        "tolerance": 1e-6,
        "search_bound": 0.80,
        "bound_loss_pct": 0.42,
        "method": "binary_search",
        "message": None,
    },
}

EXAMPLE_REVERSE_MULTI_REQUEST: dict[str, Any] = {
    "portfolio": EXAMPLE_PORTFOLIO,
    "target_loss_pct": 0.05,
    "factors": ["equity", "vol"],
    "weights": {"equity": 0.7, "vol": 0.3},
    "max_shock": 0.80,
}

EXAMPLE_REVERSE_MULTI_RESPONSE: dict[str, Any] = {
    "target_loss_pct": 0.05,
    "target_loss": 3100.0,
    "achieved_loss_pct": 0.05,
    "pnl": -3100.0,
    "base_market_value": 62000.0,
    "converged": True,
    "objective_l2": 0.12,
    "shocks": [
        {
            "factor": "equity",
            "required_shock": -0.14,
            "shock_unit": "relative",
            "weight": 0.7,
            "max_shock": 0.80,
        },
        {
            "factor": "vol",
            "required_shock": 0.25,
            "shock_unit": "relative",
            "weight": 0.3,
            "max_shock": 0.80,
        },
    ],
    "factors": ["equity", "vol"],
    "method": "ray_search_coordinate_descent",
    "iterations": 8,
    "message": None,
    "assumptions": [
        "Weights normalize shock search direction across selected factors."
    ],
}

EXAMPLE_HEDGE_COMPARE_REQUEST: dict[str, Any] = {
    "portfolio": EXAMPLE_PORTFOLIO,
    "hedged_portfolio": EXAMPLE_HEDGED_PORTFOLIO,
    "scenarios": [EXAMPLE_CRASH_SCENARIO],
    "methodology": "DELTA_GAMMA",
}

EXAMPLE_HEDGE_COMPARE_RESPONSE: dict[str, Any] = {
    "hedge_cost": -33900.0,
    "base_market_value": 62000.0,
    "hedged_market_value": 28100.0,
    "base_var_99": 12500.0,
    "hedged_var_99": 7200.0,
    "base_expected_shortfall_99": 18200.0,
    "hedged_expected_shortfall_99": 10500.0,
    "var_improvement": 5300.0,
    "es_improvement": 7700.0,
    "methodology": "DELTA_GAMMA",
    "factor_exposure_changes": [
        {
            "factor": "SPY",
            "factor_type": "equity",
            "bucket": "spot",
            "before": 56500.0,
            "after": 22600.0,
            "delta": -33900.0,
        }
    ],
    "scenarios": [
        {
            "scenario": "Equity crash −20%",
            "base_pnl": -8500.0,
            "hedged_pnl": -3400.0,
            "improvement": 5100.0,
            "base_loss": 8500.0,
            "hedged_loss": 3400.0,
            "loss_improvement": 5100.0,
        }
    ],
}

STRESS_BODY_EXAMPLES = PORTFOLIO_BODY_EXAMPLES

# Formal Scenario wire (M3.8) — illustrative; amounts are bump units, not goldens.
EXAMPLE_FORMAL_SCENARIO: dict[str, Any] = {
    "id": "formal-equity-vol",
    "name": "Equity −10% + vol +25%",
    "category": "factor",
    "description": "Illustrative formal Scenario wire",
    "shocks": [
        {"factor_type": "equity", "key": "SPY", "amount": -0.10, "bucket": "SPY"},
        {
            "factor_type": "vol",
            "key": "SPY:VOL",
            "amount": 0.25,
            "bucket": "SPY",
            "expiry": "GENERIC",
            "moneyness": "ATM",
        },
    ],
    "max_loss_pct": 0.05,
    "severity": None,
    "metadata": {},
}

EXAMPLE_FORMAL_CUSTOM_STRESS_REQUEST: dict[str, Any] = {
    "portfolio": EXAMPLE_PORTFOLIO,
    "scenarios": [EXAMPLE_FORMAL_SCENARIO],
}

FORMAL_CUSTOM_STRESS_BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "formal_equity_vol": _ex(
        "Custom stress with formal Scenario wire (M3.8)",
        EXAMPLE_FORMAL_CUSTOM_STRESS_REQUEST,
    ),
}

REVERSE_BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "equity_target_loss": _ex(
        "Single-factor reverse stress", EXAMPLE_REVERSE_REQUEST
    ),
}

REVERSE_MULTI_BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "equity_vol": _ex(
        "Multi-factor reverse stress", EXAMPLE_REVERSE_MULTI_REQUEST
    ),
}

HEDGE_COMPARE_BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "flatten_equity": _ex(
        "Compare base vs reduced equity hedge", EXAMPLE_HEDGE_COMPARE_REQUEST
    ),
}

EXAMPLE_FORMAL_HEDGE_COMPARE_REQUEST: dict[str, Any] = {
    "portfolio": EXAMPLE_PORTFOLIO,
    "hedged_portfolio": EXAMPLE_HEDGED_PORTFOLIO,
    "scenarios": [
        {
            "id": "Crash",
            "name": "Crash",
            "category": "factor",
            "shocks": [
                {
                    "factor_type": "equity",
                    "key": "SPY",
                    "amount": -0.20,
                    "bucket": "SPY",
                }
            ],
            "max_loss_pct": None,
            "severity": None,
            "metadata": {},
        }
    ],
    "methodology": "DELTA_GAMMA",
}

FORMAL_HEDGE_COMPARE_BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "flatten_equity_formal": _ex(
        "Compare base vs reduced equity hedge (formal Scenario wire)",
        EXAMPLE_FORMAL_HEDGE_COMPARE_REQUEST,
    ),
}

RESP_STRESS = {
    200: success_response(
        "Stress P&L by scenario",
        {"illustrative": _ex("Illustrative stress results", EXAMPLE_STRESS_RESPONSE)},
    ),
    422: RESP_422,
}

RESP_REVERSE = {
    200: success_response(
        "Required factor shock for target loss",
        {"illustrative": _ex("Illustrative reverse-stress result", EXAMPLE_REVERSE_RESPONSE)},
    ),
    422: RESP_422,
}

RESP_REVERSE_MULTI = {
    200: success_response(
        "Multi-factor reverse-stress solution",
        {
            "illustrative": _ex(
                "Illustrative multi-factor reverse-stress result",
                EXAMPLE_REVERSE_MULTI_RESPONSE,
            )
        },
    ),
    422: RESP_422,
}

RESP_HEDGE_COMPARE = {
    200: success_response(
        "HedgeComparisonReport — VaR/ES improvement and scenario P&L",
        {
            "illustrative": _ex(
                "Illustrative hedge comparison", EXAMPLE_HEDGE_COMPARE_RESPONSE
            )
        },
    ),
    422: RESP_422,
}


# --- Change attribution ----------------------------------------------------------

EXAMPLE_CHANGE_ATTR_REQUEST: dict[str, Any] = {
    "previous_portfolio": EXAMPLE_PORTFOLIO,
    "current_portfolio": {
        **EXAMPLE_PORTFOLIO,
        "positions": [
            {
                **EXAMPLE_PORTFOLIO["positions"][0],
                "quantity": 150.0,
            },
            EXAMPLE_PORTFOLIO["positions"][1],
        ],
    },
    "metric": "var_99",
    "methodology": "DELTA_GAMMA",
}

EXAMPLE_CHANGE_ATTR_RESPONSE: dict[str, Any] = {
    "metric": "var_99",
    "previous_risk": 12500.0,
    "current_risk": 16800.0,
    "total_change": 4300.0,
    "explained_change": 4100.0,
    "residual": 200.0,
    "items": [
        {"driver": "position_quantity:eq-spy", "delta_risk": 3800.0},
        {"driver": "market_marks", "delta_risk": 300.0},
    ],
}

CHANGE_ATTR_BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "quantity_increase": _ex(
        "VaR change after increasing equity size", EXAMPLE_CHANGE_ATTR_REQUEST
    ),
}

RESP_CHANGE_ATTR = {
    200: success_response(
        "Risk-metric change waterfall (not P&L Explain)",
        {
            "illustrative": _ex(
                "Illustrative risk-change attribution", EXAMPLE_CHANGE_ATTR_RESPONSE
            )
        },
    ),
    422: RESP_422,
}


# --- Limits drill-down -----------------------------------------------------------

EXAMPLE_LIMITS_DRILLDOWN_REQUEST: dict[str, Any] = {
    "portfolio": EXAMPLE_PORTFOLIO,
    "metric": "var_99",
    "hierarchy": {
        "level": "desk",
        "firm": "QuantLineage",
        "desk": "Global Macro",
    },
    "top_n": 5,
    "breaches_only": False,
}

EXAMPLE_LIMITS_DRILLDOWN_RESPONSE: dict[str, Any] = {
    "portfolio_id": "demo-book",
    "hierarchy_node": "QuantLineage / Global Macro",
    "hierarchy_level": "desk",
    "items": [
        {
            "hierarchy_node": "QuantLineage / Global Macro",
            "hierarchy_level": "desk",
            "metric": "var_99",
            "value": 12500.0,
            "limit": 10000.0,
            "utilization_pct": 125.0,
            "breached": True,
            "status": "BREACH",
            "warning_threshold_pct": 80.0,
            "scope": "desk",
            "label": "Desk VaR 99",
            "contributors": [
                {
                    "position_id": "eq-spy",
                    "label": "eq-spy",
                    "risk_amount": 9200.0,
                    "contribution_pct": 73.6,
                }
            ],
        }
    ],
}

LIMITS_DRILLDOWN_BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "desk_var": _ex(
        "Drill into desk VaR utilization", EXAMPLE_LIMITS_DRILLDOWN_REQUEST
    ),
}

RESP_LIMITS_DRILLDOWN = {
    200: success_response(
        "Limit breach drill-down with top contributors",
        {
            "illustrative": _ex(
                "Illustrative limits drill-down", EXAMPLE_LIMITS_DRILLDOWN_RESPONSE
            )
        },
    ),
    400: RESP_400,
    422: RESP_422,
}


# --- Risk runs -------------------------------------------------------------------

EXAMPLE_RISK_RUN_CREATE: dict[str, Any] = {
    "portfolio": EXAMPLE_PORTFOLIO,
    "run_type": "var",
    "request": {"methodology": "DELTA_GAMMA"},
    "market_snapshot_id": None,
}

EXAMPLE_RISK_RUN_QUEUED: dict[str, Any] = {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "portfolio_id": "demo-book",
    "market_snapshot_id": None,
    "status": "QUEUED",
    "run_type": "var",
    "request": {"methodology": "DELTA_GAMMA"},
    "pricing_engine_version": None,
    "methodology": None,
    "scenario_set": [],
    "error_message": None,
    "created_at": "2026-09-02T17:00:00+00:00",
    "started_at": None,
    "finished_at": None,
    "duration_seconds": None,
    "results": [],
}

EXAMPLE_RISK_RUN_COMPLETED: dict[str, Any] = {
    **EXAMPLE_RISK_RUN_QUEUED,
    "status": "COMPLETED",
    "methodology": "DELTA_GAMMA",
    "pricing_engine_version": "builtin-0.3.0",
    "started_at": "2026-09-02T17:00:00.100000+00:00",
    "finished_at": "2026-09-02T17:00:01.250000+00:00",
    "duration_seconds": 1.15,
    "results": [
        {
            "result_type": "var",
            "payload": EXAMPLE_VAR_RESPONSE,
        }
    ],
}

RISK_RUN_CREATE_BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "var_run": _ex("Enqueue historical VaR run", EXAMPLE_RISK_RUN_CREATE),
}

RESP_RISK_RUN_CREATE = {
    202: success_response(
        "Run accepted (QUEUED); poll GET /risk/runs/{id}",
        {"queued": _ex("Accepted risk run", EXAMPLE_RISK_RUN_QUEUED)},
    ),
    400: RESP_400,
    422: RESP_422,
}

RESP_RISK_RUN_GET = {
    200: success_response(
        "Risk-run status and optional result payloads",
        {
            "completed": _ex("Completed risk run", EXAMPLE_RISK_RUN_COMPLETED),
            "queued": _ex("Still queued", EXAMPLE_RISK_RUN_QUEUED),
        },
    ),
    404: RESP_404,
}


EXAMPLE_RISK_RUN_COMPARE_REQUEST: dict[str, Any] = {
    "t0_run_id": "run-t0",
    "t1_run_id": "run-t1",
    "metric": "var_99",
}

EXAMPLE_RISK_CHANGE_REPORT: dict[str, Any] = {
    "t0_run_id": "run-t0",
    "t1_run_id": "run-t1",
    "metric": "var_99",
    "unit": "currency loss",
    "sign_convention": "positive total_change means the selected metric increased (more loss-risk for VaR/ES)",
    "currency_convention": "T0/T1 portfolio currencies; this report does not FX-convert",
    "previous_risk": 10000.0,
    "current_risk": 12500.0,
    "total_change": 2500.0,
    "portfolio_trade_change": 1800.0,
    "market_change": 600.0,
    "explained_change": 2400.0,
    "residual": 100.0,
    "residual_name": "residual / interactions",
    "disclosed_changes": [],
    "identity": {
        "changed_fields": ["market_snapshot_id"],
        "t0": {
            "run_id": "run-t0",
            "portfolio_id": "demo-book",
            "portfolio_version": 1,
            "market_snapshot_id": "snap-t0",
            "as_of": "current",
            "historical_dataset_id": "demo-multi-factor-history",
            "historical_dataset_version": "v1",
            "pricing_engine_version": "builtin-0.3.0",
            "methodology": "DELTA_GAMMA",
            "scenario_set": [],
            "calculation_config": None,
            "status": "COMPLETED",
        },
        "t1": {
            "run_id": "run-t1",
            "portfolio_id": "demo-book",
            "portfolio_version": 1,
            "market_snapshot_id": "snap-t1",
            "as_of": "current",
            "historical_dataset_id": "demo-multi-factor-history",
            "historical_dataset_version": "v1",
            "pricing_engine_version": "builtin-0.3.0",
            "methodology": "DELTA_GAMMA",
            "scenario_set": [],
            "calculation_config": None,
            "status": "COMPLETED",
        },
    },
    "factor_contributors": [
        {
            "factor_id": "EquitySpot:SPY",
            "factor_type": "equity",
            "factor": "SPY",
            "bucket": "SPY",
            "delta_risk": 600.0,
        }
    ],
    "hierarchy_contributors": [
        {
            "level": "firm",
            "name": "QuantLineage",
            "path": "QuantLineage",
            "delta_risk": 1800.0,
            "position_id": None,
            "children": [],
        }
    ],
    "items": [
        {"driver": "Position change eq-spy", "delta_risk": 1800.0},
        {"driver": "EquitySpot:SPY", "delta_risk": 600.0},
        {"driver": "residual / interactions", "delta_risk": 100.0},
    ],
}

RISK_RUN_COMPARE_BODY_EXAMPLES: dict[str, dict[str, Any]] = {
    "var_increase": _ex("Compare two completed RiskRuns", EXAMPLE_RISK_RUN_COMPARE_REQUEST),
}

RESP_RISK_RUN_COMPARE = {
    200: success_response(
        "Two-RiskRun risk-change explain (not a regulatory P&L-explain certification)",
        {"illustrative": _ex("Illustrative RiskChangeReport", EXAMPLE_RISK_CHANGE_REPORT)},
    ),
    400: RESP_400,
    404: RESP_404,
    422: RESP_422,
}


# Paths covered by M7.4 (legacy; dual-mounted under /api/v1 as well).
CRITICAL_OPENAPI_PATHS: tuple[tuple[str, str], ...] = (
    ("post", "/risk/var"),
    ("post", "/risk/es"),
    ("post", "/risk/what-if"),
    ("post", "/risk/stress"),
    ("post", "/risk/stress/reverse"),
    ("post", "/risk/stress/reverse/multi"),
    ("post", "/risk/stress/compare"),
    ("post", "/risk/stress/formal/compare"),
    ("post", "/risk/change-attribution"),
    ("post", "/risk/limits/drilldown"),
    ("post", "/risk/runs"),
    ("get", "/risk/runs/{run_id}"),
    ("post", "/risk/runs/compare"),
)

# M7.3: OpenAPI component schema names expected for response_model= on critical paths.
# For array responses, ``items_schema`` is the element model name.
TYPED_RESPONSE_SCHEMAS: tuple[tuple[str, str, str, str | None], ...] = (
    # method, path, schema_name, items_schema (None = object body)
    ("post", "/risk/var", "VaRReport", None),
    ("post", "/risk/es", "ESContributionReport", None),
    ("post", "/risk/what-if", "WhatIfReport", None),
    ("post", "/risk/stress", "StressResult", "StressResult"),
    ("post", "/risk/stress/reverse", "ReverseStressResult", None),
    ("post", "/risk/stress/reverse/multi", "MultiFactorReverseStressResult", None),
    ("post", "/risk/stress/compare", "HedgeComparisonReport", None),
    ("post", "/risk/stress/formal/compare", "HedgeComparisonReport", None),
    ("post", "/risk/change-attribution", "RiskChangeAttributionReport", None),
    ("post", "/risk/limits/drilldown", "LimitDrilldownReport", None),
    ("post", "/risk/runs", "RiskRunView", None),
    ("get", "/risk/runs/{run_id}", "RiskRunView", None),
    ("post", "/risk/runs/compare", "RiskChangeReport", None),
)
