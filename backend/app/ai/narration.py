"""Typed claim grounding for bounded multi-tool investigations.

Every quantitative token in model prose must bind to a grounding manifest
entry (metric, value, unit, source field). Dates, ids, years, counts, and
unrelated metadata cannot ground VaR or Greek claims. On rejection, callers
replace narration with deterministic formatting.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field

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

_METRIC_WINDOW = 48
_METRIC_HINTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:expected\s+shortfall|shortfall|\bes\b)", re.I), "es"),
    (re.compile(r"\b(?:value at risk|var)\b", re.I), "var"),
    (re.compile(r"\bgamma\b", re.I), "gamma"),
    (re.compile(r"\bvega\b", re.I), "vega"),
    (re.compile(r"\bdv01\b", re.I), "dv01"),
    (re.compile(r"\bdelta\b", re.I), "delta"),
    (re.compile(r"\b(?:contribution|contributor|share)\b", re.I), "contribution"),
    (re.compile(r"\butilization\b", re.I), "utilization"),
    (re.compile(r"\blimit\b", re.I), "limit"),
    (re.compile(r"\b(?:worst\s+)?loss\b", re.I), "stress_loss"),
    (re.compile(r"\bconfidence\b", re.I), "confidence"),
)
_ABS_LOSS_CONVENTIONS = frozenset(
    {
        "absolute_loss",
        "abs_loss",
        "absolute_loss_display",
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
    """Accept narration only when every numeric token binds to a typed claim."""
    text = (narration or "").strip()
    if not text:
        return NarrationGroundingResult(accepted=True, narration=None)

    tokens = list(_NUMERIC_TOKEN_RE.finditer(text))
    if not tokens:
        return NarrationGroundingResult(accepted=True, narration=text)

    manifests = _manifests_from_source(payloads)
    rejected: list[str] = []
    for match in tokens:
        token = match.group(0)
        metric = _claimed_metric(text, match)
        if not _token_grounded(token, metric, manifests):
            rejected.append(token)

    if rejected:
        return NarrationGroundingResult(
            accepted=False,
            narration=None,
            rejected_tokens=rejected,
        )
    return NarrationGroundingResult(accepted=True, narration=text)


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
            )
        )
        return
    if isinstance(value, str):
        return
    if isinstance(value, dict):
        local = dict(ctx)
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
        return ("delta", "greek", False)
    if k in _GREEK_KEYS:
        return (k, "greek", False)
    if k == "value":
        greek = ctx.get("greek")
        if isinstance(greek, str) and greek in _GREEK_KEYS:
            return (greek, "greek", False)
        metric = ctx.get("metric")
        if isinstance(metric, str):
            if "var" in metric:
                return ("var", "currency", False)
            if "es" in metric or "shortfall" in metric:
                return ("es", "currency", False)
            if metric.endswith("_pct"):
                return ("percent", "percent", False)
        return ("market_value", "currency", False)
    return None


def _claimed_metric(text: str, match: re.Match[str]) -> str | None:
    token = match.group(0)
    start, end = match.span()
    if token.endswith("%"):
        after = text[end : end + 16]
        if re.search(r"^\s*(?:historical\s+)?(?:var|es|expected\s+shortfall)\b", after, re.I):
            return "confidence"
        before = text[max(0, start - 16) : start]
        if re.search(r"\b(?:var|es)\b\s*$", before, re.I):
            return "confidence"

    window_start = max(0, start - _METRIC_WINDOW)
    window = text[window_start : min(len(text), end + _METRIC_WINDOW)]
    best: str | None = None
    best_key: tuple[int, int] | None = None
    for pattern, metric in _METRIC_HINTS:
        for hint in pattern.finditer(window):
            hint_start = window_start + hint.start()
            hint_end = window_start + hint.end()
            if hint_end <= start:
                key = (0, start - hint_end)
            elif hint_start >= end:
                key = (1, hint_start - end)
            else:
                key = (0, 0)
            if best_key is None or key < best_key:
                best_key = key
                best = metric
    if token.endswith("%") and best == "var":
        return "confidence"
    return best


def _token_grounded(
    token: str,
    claimed_metric: str | None,
    manifests: Sequence[GroundingClaim],
) -> bool:
    token_is_percent = token.strip().endswith("%")
    try:
        token_value = float(token.strip().replace(",", "").rstrip("%"))
    except ValueError:
        return False

    for claim in manifests:
        if not _metric_compatible(claimed_metric, claim):
            continue
        if _value_matches(claim, token_value, token_is_percent=token_is_percent):
            return True
    return False


def _metric_compatible(claimed: str | None, claim: GroundingClaim) -> bool:
    if claim.metric not in _FINANCIAL_METRICS:
        return False
    if claimed is None:
        return False
    return claimed == claim.metric


def _value_matches(claim: GroundingClaim, token_value: float, *, token_is_percent: bool) -> bool:
    candidates: list[float] = []
    if token_is_percent:
        if claim.unit == "percent":
            candidates.append(claim.value)
        elif claim.allow_percent_from_fraction and claim.unit == "ratio":
            candidates.append(claim.value * 100.0)
        else:
            return False
    else:
        if claim.unit in {"year", "count", "identifier", "date"}:
            return False
        candidates.append(claim.value)

    for candidate in candidates:
        if _numeric_close(candidate, token_value):
            return True
        if (
            claim.sign_convention in _ABS_LOSS_CONVENTIONS
            and _numeric_close(abs(candidate), token_value)
        ):
            return True
    return False


def _numeric_close(actual: float, token: float) -> bool:
    if abs(actual - token) <= 1e-6:
        return True
    if abs(token - round(token)) <= 1e-9 and abs(round(actual) - token) <= 1e-9:
        return True
    for decimals in (1, 2):
        if abs(round(actual, decimals) - token) <= 1e-9:
            return True
    scale = max(abs(actual), 1.0)
    return abs(actual - token) / scale <= 1e-4


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
