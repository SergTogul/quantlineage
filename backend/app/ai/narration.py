"""Numeric narration grounding for bounded multi-tool investigations (T22).

Milestone 2 may narrate tool results, but every numeric token in model prose must
appear in (or be deterministically formatted from) executed tool payloads.
Otherwise QuantLineage replaces the narration with deterministic formatting.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

from pydantic import BaseModel, ConfigDict, Field

_NUMERIC_TOKEN_RE = re.compile(
    r"(?<![A-Za-z_])"
    r"[-+]?"
    r"(?:\d{1,3}(?:,\d{3})+|\d+)"
    r"(?:\.\d+)?"
    r"%?"
)


class NarrationGroundingResult(BaseModel):
    """Outcome of validating model narration against tool payloads."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool
    narration: str | None = None
    rejected_tokens: list[str] = Field(default_factory=list)


def extract_numeric_tokens(text: str) -> list[str]:
    """Return numeric tokens as they appear in ``text`` (order preserved)."""
    if not text:
        return []
    return [match.group(0) for match in _NUMERIC_TOKEN_RE.finditer(text)]


def collect_allowed_numeric_tokens(payloads: Sequence[Any]) -> set[str]:
    """Collect allowed numeric spellings from tool payloads and derived formats."""
    allowed: set[str] = set()
    for payload in payloads:
        _walk_collect(payload, allowed)
    return allowed


def ground_narration(
    narration: str,
    payloads: Sequence[Any],
) -> NarrationGroundingResult:
    """Accept narration only when every numeric token is grounded in payloads."""
    text = (narration or "").strip()
    if not text:
        return NarrationGroundingResult(accepted=True, narration=None)

    tokens = extract_numeric_tokens(text)
    if not tokens:
        return NarrationGroundingResult(accepted=True, narration=text)

    allowed = collect_allowed_numeric_tokens(payloads)
    allowed_normalized = {_normalize_token(token) for token in allowed}
    rejected: list[str] = []
    for token in tokens:
        if _normalize_token(token) not in allowed_normalized:
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
        return _format_answer(name, tool_output, card=card)
    return None


def _walk_collect(value: Any, allowed: set[str]) -> None:
    if isinstance(value, bool):
        return
    if isinstance(value, int | float):
        _add_number_forms(allowed, value)
        return
    if isinstance(value, str):
        for token in extract_numeric_tokens(value):
            allowed.add(token)
            _add_normalized_forms(allowed, token)
        return
    if isinstance(value, dict):
        for nested in value.values():
            _walk_collect(nested, allowed)
        return
    if isinstance(value, (list, tuple, set)):
        for nested in value:
            _walk_collect(nested, allowed)


def _add_number_forms(allowed: set[str], value: int | float) -> None:
    number = float(value)
    candidates: Iterable[str] = (
        str(value),
        str(number),
        f"{number:g}",
        f"{number:.0f}",
        f"{number:.1f}",
        f"{number:.2f}",
        f"{number:,.0f}",
        f"{number:,.1f}",
        f"{number:,.2f}",
    )
    for item in candidates:
        allowed.add(item)
        _add_normalized_forms(allowed, item)

    if 0 < abs(number) <= 1:
        percent = abs(number) * 100
        for item in (
            f"{percent:g}",
            f"{percent:.0f}",
            f"{percent:.1f}",
            f"{percent:.0f}%",
            f"{percent:.1f}%",
            f"{percent:g}%",
        ):
            allowed.add(item)
            _add_normalized_forms(allowed, item)


def _add_normalized_forms(allowed: set[str], token: str) -> None:
    normalized = _normalize_token(token)
    if normalized:
        allowed.add(normalized)


def _normalize_token(token: str) -> str:
    raw = token.strip().replace(",", "")
    if raw.endswith("%"):
        body = raw[:-1]
        try:
            return f"{float(body):g}%"
        except ValueError:
            return raw.lower()
    try:
        return f"{float(raw):g}"
    except ValueError:
        return raw.lower()
