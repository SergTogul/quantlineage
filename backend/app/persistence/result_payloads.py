"""Typed ``risk_results.payload`` validation (R0.8.7 / RF-013 cell 4 / PERF-016).

Physical JSON column remains. Writes must match a known ``result_type`` schema
(``extra='forbid'``). Uses existing domain/API result models; list run types
keep the worker ``{"items": [...]}`` envelope from ``_serialize_result``.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.api.schemas.transport import RiskQueryResponse
from app.domain.models import (
    AttributionReport,
    Contributor,
    ESContributionReport,
    HedgeComparisonReport,
    HierarchyNode,
    LimitResult,
    MultiFactorReverseStressResult,
    Portfolio,
    ReverseStressResult,
    RiskChangeAttributionReport,
    RiskFactorExposure,
    RiskSummary,
    ScenarioEvaluationReport,
    StressResult,
    VaRMethodologyComparison,
    VaRReport,
)


def _forbid_extra(model: type[BaseModel]) -> type[BaseModel]:
    """Reuse an existing result model with extra keys rejected."""

    class Strict(model):
        model_config = ConfigDict(extra="forbid", title=model.__name__)

    Strict.__name__ = model.__name__
    Strict.__qualname__ = model.__name__
    Strict.__doc__ = model.__doc__
    return Strict


class StressResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[StressResult]


class FactorExposurePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[RiskFactorExposure]


class LimitResultPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[LimitResult]


class ContributorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[Contributor]


class DashboardResultPayload(BaseModel):
    """Same keys as ``DashboardBatchResponse``; domain types only (no API cycle)."""

    model_config = ConfigDict(extra="forbid")

    portfolio: Portfolio
    summary: RiskSummary
    stress: list[StressResult]
    threats: ScenarioEvaluationReport
    contributors: list[Contributor]
    limits: list[LimitResult]
    factors: list[RiskFactorExposure]
    varReport: VaRReport
    hierarchy: HierarchyNode
    attribution: AttributionReport


RISK_RESULT_PAYLOAD_SCHEMAS: Mapping[str, type[BaseModel]] = MappingProxyType(
    {
        "summary": _forbid_extra(RiskSummary),
        "var": _forbid_extra(VaRReport),
        "stress": StressResultPayload,
        "factors": FactorExposurePayload,
        "limits": LimitResultPayload,
        "hierarchy": _forbid_extra(HierarchyNode),
        "contributors": ContributorPayload,
        "dashboard": DashboardResultPayload,
        "stress_evaluate": _forbid_extra(ScenarioEvaluationReport),
        "reverse_stress": _forbid_extra(ReverseStressResult),
        "reverse_stress_multi": _forbid_extra(MultiFactorReverseStressResult),
        "stress_compare": _forbid_extra(HedgeComparisonReport),
        "query": _forbid_extra(RiskQueryResponse),
        "attribution": _forbid_extra(AttributionReport),
        "attribution_demo": _forbid_extra(AttributionReport),
        "change_attribution": _forbid_extra(RiskChangeAttributionReport),
        "es": _forbid_extra(ESContributionReport),
        "var_compare": _forbid_extra(VaRMethodologyComparison),
    }
)


def _reject_unknown_keys(raw: Any, dumped: Any, *, path: str = "payload") -> None:
    """Fail closed on nested extra keys that child models still ignore."""
    if isinstance(raw, Mapping):
        if not isinstance(dumped, Mapping):
            return
        extra = sorted(set(raw) - set(dumped))
        if extra:
            raise ValueError(f"unexpected keys on {path}: {extra}")
        for key, value in raw.items():
            _reject_unknown_keys(value, dumped[key], path=f"{path}.{key}")
    elif isinstance(raw, list) and isinstance(dumped, list):
        for i, (left, right) in enumerate(zip(raw, dumped)):
            _reject_unknown_keys(left, right, path=f"{path}[{i}]")


def parse_result_payload(result_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate ``payload`` for ``result_type``; return a JSON-object copy.

    Unknown ``result_type`` or extra keys fail closed. Canonical dump is used
    only to detect extras; the stored dict is the caller payload (numerical
    identity vs ``execute_run_type``).
    """
    key = (result_type or "").strip()
    schema = RISK_RESULT_PAYLOAD_SCHEMAS.get(key)
    if schema is None:
        raise ValueError(
            f"unknown result_type {result_type!r}; "
            f"supported: {sorted(RISK_RESULT_PAYLOAD_SCHEMAS)}"
        )
    if not isinstance(payload, Mapping) or isinstance(payload, (str, bytes)):
        raise ValueError("result payload must be a JSON object")
    raw = dict(payload)
    typed = schema.model_validate(raw)
    _reject_unknown_keys(raw, typed.model_dump(mode="json"))
    return raw
