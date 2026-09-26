"""Server-issued claim selection: free-text financial assertions are never trusted."""

import json

import pytest

from app.ai.narration import (
    GroundingClaim,
    build_grounding_manifest,
    claim_catalogue,
    ground_narration,
)


def selection(payloads):
    return json.dumps({"claim_ids": list(claim_catalogue(payloads))[:32]})


@pytest.mark.parametrize("text", [
    "VaR is $50 million.", "VaR is $50.", "VaR is fifty million dollars.",
    "No limits are breached.", "Risk decreased.", "Position B has the largest delta.",
    "Delta for position B is 50.", "Contribution is $50.", "Confidence is USD 0.5.",
    "Delta is 50 dollars.", "VaR is 50 percent.", "VaR is 50 per bp.",
    "Contribution is $50%.", "Investigation complete.", "", "{}",
])
def test_unstructured_claims_fail_closed(text):
    facts = [{"var": 50, "contribution_pct": 50, "confidence": .5,
              "positions": [{"position_id": "A", "delta": 50}, {"position_id": "B", "delta": 10}]}]
    assert not ground_narration(text, facts).accepted


def test_selected_claims_render_exact_server_values_and_qualifiers():
    facts = build_grounding_manifest("get_var_es", {
        "portfolio_id": "book-A", "market_snapshot_id": "snapshot-A", "currency": "USD",
        "methods": [{"method": "historical", "var": 50, "confidence": .99}],
    })
    result = ground_narration(selection(facts), facts)
    assert result.accepted
    assert "- var: 50 currency" in result.narration
    assert 'entity="book-A"' in result.narration
    assert 'snapshot_or_run="snapshot-A"' in result.narration
    assert 'source="get_var_es"' in result.narration
    assert 'method="historical"' in result.narration
    assert "confidence=0.99" in result.narration
    assert 'currency="USD"' in result.narration
    assert "million" not in result.narration


def test_wrong_entity_and_stale_source_references_rejected():
    a = build_grounding_manifest("get_position_greeks", {"position_id": "A", "delta": 50})
    b = build_grounding_manifest("get_position_greeks", {"position_id": "B", "delta": 50})
    assert set(claim_catalogue(a)).isdisjoint(claim_catalogue(b))
    assert not ground_narration(selection(a), b).accepted
    catalogue = claim_catalogue(a + b)
    b_id = next(key for key, claim in catalogue.items() if claim.entity_id == "B")
    result = ground_narration(json.dumps({"claim_ids": [b_id]}), a + b)
    assert 'entity="B"' in result.narration
    old = build_grounding_manifest("get_var_es", {"run_id": "old", "var": 50})
    new = build_grounding_manifest("get_var_es", {"run_id": "new", "var": 50})
    assert not ground_narration(selection(old), new).accepted


@pytest.mark.parametrize("unit", ["currency", "percent", "ratio", "per_bp", "greek"])
def test_units_and_sign_are_preserved_exactly(unit):
    claim = GroundingClaim(metric="delta", value=-50.125, unit=unit, field_path="delta")
    result = ground_narration(selection([claim]), [claim])
    assert result.accepted
    assert f"- delta: -50.125 {unit}" in result.narration
    changed = claim.model_copy(update={"unit": "other"})
    assert not ground_narration(selection([claim]), [changed]).accepted


@pytest.mark.parametrize("override", [
    {"answer": "No limits are breached"}, {"entity_id": "B"},
    {"value": 50000000}, {"unit": "EUR"}, {"scale": "million"},
])
def test_model_cannot_override_any_claim_fields(override):
    facts = [{"var": 50}]
    response = {"claim_ids": list(claim_catalogue(facts)), **override}
    assert not ground_narration(json.dumps(response), facts).accepted


def test_unknown_empty_and_oversized_selection_rejected():
    facts = [{"var": 50}]
    key = next(iter(claim_catalogue(facts)))
    for ids in ([], ["unknown"], [key, "unknown"], [key] * 33):
        assert not ground_narration(json.dumps({"claim_ids": ids}), facts).accepted
    assert not ground_narration(selection(facts), []).accepted


def test_nonfinite_values_never_receive_claim_ids():
    for value in (float("nan"), float("inf"), float("-inf")):
        assert claim_catalogue([{"var": value}]) == {}
