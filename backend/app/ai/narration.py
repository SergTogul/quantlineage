"""Validate server-issued claim references and render facts deterministically.

Free-form model prose is never accepted as grounded. IDs bind the full fact,
including its value, entity, unit, qualifiers, source field and run/snapshot.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

_NUMERIC_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"[-+]?"
    r"(?:\d{1,3}(?:,\d{3})+|\d+)"
    r"(?:\.\d+)?"
    r"%?"
)

_ID_KEYS = frozenset(
    {
        "id",
        "run_id",
        "risk_run_id",
        "portfolio_id",
        "position_id",
        "instrument_id",
        "market_snapshot_id",
        "historical_dataset_id",
        "t0_run_id",
        "t1_run_id",
        "call_id",
    }
)
_YEAR_KEYS = frozenset({"year", "as_of_year"})
_COUNT_KEYS = frozenset({"count", "n", "top_n", "observations", "rounds_used"})
_VAR_KEYS = frozenset({"var", "var_95", "var_99"})
_ES_KEYS = frozenset({"expected_shortfall", "es", "es_95", "es_99", "expected_shortfall_99"})
_GREEK_KEYS = frozenset({"delta", "gamma", "vega", "dv01", "fx_delta", "theta", "rho"})
_FINANCIAL_METRICS = frozenset(
    {
        "var",
        "es",
        "delta",
        "gamma",
        "vega",
        "dv01",
        "fx_delta",
        "confidence",
        "contribution",
        "utilization",
        "stress_loss",
        "limit",
        "risk_change",
        "market_value",
        "percent",
    }
)

_MISSING_ON_PAYLOAD = "not on this payload"
_MISSING_ON_PAYLOAD_RE = re.compile(re.escape(_MISSING_ON_PAYLOAD), re.I)


class GroundingClaim(BaseModel):
    """One typed quantitative fact from a successful tool result."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    value: float
    unit: str
    sign_convention: str | None = None
    entity_id: str | None = None
    source_tool: str | None = None
    field_path: str
    snapshot_or_run_id: str | None = None
    allow_percent_from_fraction: bool = False
    qualifiers: dict[str, Any] = Field(default_factory=dict)


class NarrationGroundingResult(BaseModel):
    """Outcome of validating model narration against typed claims."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool
    narration: str | None = None
    rejected_tokens: list[str] = Field(default_factory=list)


def extract_numeric_tokens(text: str) -> list[str]:
    """Return numeric tokens as they appear in ``text`` (order preserved)."""
    if not text:
        return []
    return [match.group(0) for match in _NUMERIC_TOKEN_RE.finditer(text)]


def build_grounding_manifest(
    tool_name: str | None,
    payload: dict[str, Any],
) -> list[GroundingClaim]:
    """Walk a tool payload and emit typed claims (no id/date token harvesting)."""
    claims: list[GroundingClaim] = []
    identity = _identity_from_payload(payload)
    _walk_payload(
        payload,
        path=[],
        claims=claims,
        ctx={"tool": tool_name, **identity},
    )
    return claims


def collect_allowed_numeric_tokens(payloads: Sequence[Any]) -> set[str]:
    """Deprecated compatibility wrapper; only financial claim values are allowed."""
    allowed: set[str] = set()
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for claim in build_grounding_manifest(None, payload):
            if claim.metric not in _FINANCIAL_METRICS:
                continue
            _add_claim_forms(allowed, claim)
    return allowed


def ground_narration(
    narration: str,
    payloads: Sequence[Any],
) -> NarrationGroundingResult:
    """Validate references, never model-written financial prose or conclusions."""
    try:
        selection = ClaimSelection.model_validate_json(narration, strict=True)
    except (ValidationError, ValueError):
        return NarrationGroundingResult(accepted=False, narration=None,
                                       rejected_tokens=extract_numeric_tokens(narration))
    claims = claim_catalogue(payloads)
    if any(key not in claims for key in selection.claim_ids):
        return NarrationGroundingResult(accepted=False, narration=None)
    # IDs bind the entire server-side record. The model cannot replace a value,
    # entity, scale, source, or unit and cannot append qualitative conclusions.
    rendered = []
    for key in dict.fromkeys(selection.claim_ids):
        claim = claims[key]
        rendered.append(_render_claim(claim))
    from app.ai.config import get_openai_api_key
    from app.ai.errors import sanitize_provider_message

    return NarrationGroundingResult(
        accepted=True,
        narration=sanitize_provider_message("Verified tool facts:\n" + "\n".join(rendered),
                                            api_key=get_openai_api_key()),
    )


class ClaimSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    claim_ids: list[str] = Field(min_length=1, max_length=32)


def claim_catalogue(payloads: Sequence[Any]) -> dict[str, GroundingClaim]:
    result = {}
    for claim in _manifests_from_source(payloads):
        if not math.isfinite(claim.value) or claim.metric not in _FINANCIAL_METRICS:
            continue
        encoded = json.dumps(claim.model_dump(), sort_keys=True).encode()
        result["claim_" + hashlib.sha256(encoded).hexdigest()] = claim
    return result


def _render_claim(claim: GroundingClaim) -> str:
    """Render one immutable claim without model-authored text or arithmetic."""
    parts = [f"- {claim.metric}: {claim.value:.12g} {claim.unit}"]
    metadata = {
        "entity": claim.entity_id,
        "source": claim.source_tool,
        "field": claim.field_path,
        "snapshot_or_run": claim.snapshot_or_run_id,
        "sign_convention": claim.sign_convention,
        **claim.qualifiers,
    }
    suffix = "; ".join(
        f"{key}={json.dumps(value, ensure_ascii=True, sort_keys=True)}"
        for key, value in sorted(metadata.items())
        if value is not None
    )
    return f"{parts[0]} ({suffix})" if suffix else parts[0]


def format_tool_turns_deterministically(tool_turns: Sequence[Any]) -> str | None:
    """Format the last successful tool turn with existing deterministic formatters."""
    from app.risk.query import RiskToolName, _format_answer, _grounded_card

    for turn in reversed(list(tool_turns)):
        tool_name = getattr(turn, "tool_name", None)
        tool_output = getattr(turn, "tool_output", None)
        tool_error = getattr(turn, "tool_error", None)
        if tool_error or not isinstance(tool_output, dict) or not tool_name:
            continue
        try:
            name = RiskToolName(str(tool_name))
        except ValueError:
            continue
        card = _grounded_card(name, tool_output)
        return _strip_missing_payload_placeholder(
            _format_answer(name, tool_output, card=card)
        )
    return None


def _manifests_from_source(payloads: Sequence[Any]) -> list[GroundingClaim]:
    manifests: list[GroundingClaim] = []
    for item in payloads:
        if isinstance(item, GroundingClaim):
            manifests.append(item)
        elif isinstance(item, dict):
            manifests.extend(build_grounding_manifest(item.get("_tool_name"), item))
    return manifests


def _identity_from_payload(payload: dict[str, Any]) -> dict[str, str | None]:
    entity = payload.get("position_id") or payload.get("portfolio_id")
    run = payload.get("risk_run_id") or payload.get("run_id") or payload.get("id")
    snapshot = payload.get("market_snapshot_id")
    return {
        "entity_id": str(entity) if entity is not None else None,
        "snapshot_or_run_id": str(run or snapshot) if (run or snapshot) is not None else None,
    }


def _walk_payload(
    value: Any,
    *,
    path: list[str],
    claims: list[GroundingClaim],
    ctx: dict[str, Any],
) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int | float):
        classified = _classify_field(path[-1] if path else "", ctx)
        if classified is None:
            return
        metric, unit, allow_percent = classified
        claims.append(
            GroundingClaim(
                metric=metric,
                value=float(value),
                unit=unit,
                sign_convention=ctx.get("sign_convention"),
                entity_id=ctx.get("entity_id"),
                source_tool=ctx.get("tool"),
                field_path=".".join(path) if path else metric,
                snapshot_or_run_id=ctx.get("snapshot_or_run_id"),
                allow_percent_from_fraction=allow_percent,
                qualifiers=dict(ctx.get("qualifiers", {})),
            )
        )
        return
    if isinstance(value, str):
        return
    if isinstance(value, dict):
        local = dict(ctx)
        qualifiers = dict(ctx.get("qualifiers", {}))
        for key in ("currency", "unit", "convention", "scale", "method", "methodology",
                    "confidence", "as_of", "portfolio_id", "market_snapshot_id",
                    "risk_run_id", "run_id", "t0_run_id", "t1_run_id"):
            if key in value and isinstance(value[key], (str, int, float)):
                qualifiers[key] = value[key]
        local["qualifiers"] = qualifiers
        if isinstance(value.get("greek"), str):
            local["greek"] = value["greek"].lower()
        if isinstance(value.get("metric"), str):
            local["metric"] = value["metric"].lower()
        if value.get("position_id") is not None:
            local["entity_id"] = str(value["position_id"])
        if value.get("sign_convention") is not None:
            local["sign_convention"] = str(value["sign_convention"])
        for key, nested in value.items():
            _walk_payload(nested, path=[*path, str(key)], claims=claims, ctx=local)
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _walk_payload(
                nested,
                path=[*path, str(index)],
                claims=claims,
                ctx=ctx,
            )


def _classify_field(key: str, ctx: dict[str, Any]) -> tuple[str, str, bool] | None:
    k = key.lower()
    if k in _ID_KEYS or k.endswith("_id"):
        return None
    if k in _YEAR_KEYS or k.endswith("_year"):
        return ("year", "year", False)
    if "date" in k or k in {"as_of", "created_at", "updated_at"}:
        return None
    if k in _COUNT_KEYS:
        return ("count", "count", False)
    if k in _VAR_KEYS:
        return ("var", "currency", False)
    if k in _ES_KEYS:
        return ("es", "currency", False)
    if k == "confidence":
        return ("confidence", "ratio", True)
    if k == "worst_loss" or k == "loss":
        return ("stress_loss", "currency", False)
    if k == "market_value":
        return ("market_value", "currency", False)
    if k in {"contribution_pct", "share_pct"}:
        return ("contribution", "percent", False)
    if k in {"utilization_pct"}:
        return ("utilization", "percent", False)
    if k.endswith("_pct") or k.endswith("_percent"):
        return ("percent", "percent", False)
    if k in {"limit"}:
        return ("limit", "currency", False)
    if k == "delta":
        if ctx.get("tool") == "compare_risk_runs":
            return ("risk_change", "currency", False)
        return ("delta", ctx.get("qualifiers", {}).get("unit", "greek"), False)
    if k in _GREEK_KEYS:
        return (k, ctx.get("qualifiers", {}).get("unit", "greek"), False)
    if k == "value":
        greek = ctx.get("greek")
        if isinstance(greek, str) and greek in _GREEK_KEYS:
            return (greek, ctx.get("qualifiers", {}).get("unit", "greek"), False)
        metric = ctx.get("metric")
        if isinstance(metric, str):
            if metric in _VAR_KEYS:
                return ("var", "currency", False)
            if metric in _ES_KEYS:
                return ("es", "currency", False)
            if metric.endswith("_pct"):
                return ("percent", "percent", False)
        return None
    return None


def _add_claim_forms(allowed: set[str], claim: GroundingClaim) -> None:
    value = claim.value
    for item in (
        f"{value:g}",
        f"{value:.0f}",
        f"{value:.1f}",
        f"{value:.2f}",
        f"{value:,.0f}",
        f"{value:,.1f}",
        f"{value:,.2f}",
    ):
        allowed.add(item)
    if claim.allow_percent_from_fraction and claim.unit == "ratio":
        percent = abs(value) * 100
        allowed.add(f"{percent:g}%")
        allowed.add(f"{percent:.0f}%")
    if claim.unit == "percent":
        allowed.add(f"{value:g}%")
        allowed.add(f"{value:.0f}%")


def _strip_missing_payload_placeholder(text: str | None) -> str | None:
    if text is None:
        return None
    cleaned = _MISSING_ON_PAYLOAD_RE.sub("", text)
    cleaned = re.sub(r"\s+;", ";", cleaned)
    cleaned = re.sub(r";\s*;", ";", cleaned)
    cleaned = re.sub(r"\s+\.", ".", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()
