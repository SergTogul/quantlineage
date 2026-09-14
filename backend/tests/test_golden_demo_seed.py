"""Stage 10.4: idempotent golden-demo seed (does not replace existing wiring seed)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

from app.persistence.session import session_scope
from app.persistence.sqlalchemy_repos import (
    SqlAlchemyLimitDefinitionRepository,
    SqlAlchemyPortfolioRepository,
    SqlAlchemyScenarioDefinitionRepository,
)
from app.sample import DEMO_PORTFOLIOS, SAMPLE_PORTFOLIO


@pytest.fixture
def sqlite_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.delenv("QUANTLINEAGE_DATABASE_URL", raising=False)
    db_path = tmp_path / "golden-demo.db"
    return f"sqlite:///{db_path}"


def _counts(url: str) -> tuple[list[str], int, int]:
    from app.demo.seed import seed_golden_demo

    report = seed_golden_demo(url=url)
    assert report["status"] == "ok"
    with session_scope(report["session_factory"]) as session:
        portfolios = SqlAlchemyPortfolioRepository(session).list_ids()
        scenarios = len(SqlAlchemyScenarioDefinitionRepository(session).list_all())
        limits = len(SqlAlchemyLimitDefinitionRepository(session).list_for_portfolio(None))
    return portfolios, scenarios, limits


def test_golden_demo_seed_inserts_catalog_once(sqlite_url: str) -> None:
    from app.demo.seed import GOLDEN_DEMO_PORTFOLIO_ID, seed_golden_demo

    first = seed_golden_demo(url=sqlite_url)
    assert first["status"] == "ok"
    assert first["default_portfolio_id"] == GOLDEN_DEMO_PORTFOLIO_ID == SAMPLE_PORTFOLIO.id
    assert first["data_class"] == "demo"
    assert first["historical_dataset_id"] == "demo-multi-factor-history"
    assert set(first["portfolio_ids"]) == {p.id for p in DEMO_PORTFOLIOS}
    assert first["inserted"]["portfolios"] >= 1

    portfolios, scenarios, limits = _counts(sqlite_url)
    assert set(portfolios) >= {p.id for p in DEMO_PORTFOLIOS}
    assert scenarios >= 1
    assert limits >= 1


def test_golden_demo_seed_is_idempotent(sqlite_url: str) -> None:
    from app.demo.seed import seed_golden_demo

    first = seed_golden_demo(url=sqlite_url)
    second = seed_golden_demo(url=sqlite_url)
    assert first["portfolio_ids"] == second["portfolio_ids"]
    assert first["scenario_count"] == second["scenario_count"]
    assert first["limit_count"] == second["limit_count"]
    assert second["inserted"]["portfolios"] == 0
    assert second["inserted"]["scenarios"] == 0
    assert second["inserted"]["limits"] == 0
    assert second["already_present"]["portfolios"] == len(first["portfolio_ids"])

    before = _counts(sqlite_url)
    after = _counts(sqlite_url)
    assert before == after


def test_demo_script_distinguishes_demo_from_observed() -> None:
    text = (ROOT / "docs" / "demo_script.md").read_text(encoding="utf-8")
    lowered = text.lower()
    assert "docker compose" in lowered
    assert "compare t0/t1" in lowered
    assert "why did my risk change" in lowered
    assert "synthetic" in lowered
    assert "observed" in lowered
    assert "not observed" in lowered or "not live" in lowered
    assert "known_limitations" in lowered or "methodology" in lowered
    assert "global-macro" in lowered


def test_golden_demo_seed_cli_json(sqlite_url: str, capsys: pytest.CaptureFixture[str]) -> None:
    from app.demo.seed import main

    assert main(["--url", sqlite_url]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert "session_factory" not in payload
    assert payload["data_class"] == "demo"

