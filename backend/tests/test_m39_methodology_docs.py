"""M3.9: multi-factor reverse-stress methodology docs stay honest.

Asserts published methodology text exists, surfaces the engine ASSUMPTIONS,
and never claims a certified global optimum.
"""

from __future__ import annotations

from pathlib import Path

from app.risk.reverse_stress_multi import ASSUMPTIONS

REPO_ROOT = Path(__file__).resolve().parents[2]
METHOD_DOC = REPO_ROOT / "docs" / "methodology" / "multi_factor_reverse_stress.md"


def test_m39_methodology_doc_exists_and_denies_global_optimum():
    assert METHOD_DOC.is_file(), f"missing methodology doc: {METHOD_DOC}"
    text = METHOD_DOC.read_text(encoding="utf-8")
    lower = text.lower()
    assert "not a certified global optimum" in lower
    assert "ray" in lower and "coordinate descent" in lower
    assert "adverse orthant" in lower
    assert "monotonicity" in lower or "monotone" in lower
    # Guard against over-claim language (allow only negated / denial forms).
    assert "is a certified global optimum" not in lower
    assert "complete optimizer" not in lower


def test_m39_methodology_doc_covers_engine_assumptions():
    text = METHOD_DOC.read_text(encoding="utf-8")
    lower = text.lower()
    required_phrases = (
        "adverse orthant",
        "l2",
        "loss",
        "monotone",
        "ray search",
        "coordinate descent",
        "global optimum",
        "wire units",
    )
    for phrase in required_phrases:
        assert phrase in lower, phrase
    assert len(ASSUMPTIONS) >= 5
    # Runtime payload assumptions must stay aligned with published limitations.
    for assumption in ASSUMPTIONS:
        assert assumption  # non-empty contract with API
    assert any("global optimum" in a.lower() for a in ASSUMPTIONS)
    assert any("orthant" in a.lower() for a in ASSUMPTIONS)
    assert any("monotone" in a.lower() for a in ASSUMPTIONS)
