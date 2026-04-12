"""R0.10.3 / RF-015 leftover: HEAVY work must not monopolize the request thread.

When Compose / production-shaped deploys set ``RISKFORGE_EXTERNAL_WORKER=1``
(or ``RISKFORGE_HEAVY_INLINE=0``), inline FULL_REVALUATION summary and the
dashboard batch refuse request-thread compute and point clients at
``POST /risk/runs``. INTERACTIVE LINEAR / DELTA_GAMMA summary stays sync.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.backpressure import RISK_RUNS_PATH, heavy_inline_allowed
from app.main import app

PUBLIC_BAD_REQUEST = "Invalid request"
RISK_RUNS = "/risk/runs"


def _assert_refused_inline(response) -> None:
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "bad_request"
    assert body["message"] == PUBLIC_BAD_REQUEST
    assert isinstance(body["details"], dict)
    assert body["details"]["use"] == RISK_RUNS


def test_full_revaluation_summary_refused_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        response = client.post(
            "/api/v1/risk/summary",
            params={"methodology": "FULL_REVALUATION"},
            json=book,
        )
        _assert_refused_inline(response)


def test_full_revaluation_summary_refused_on_legacy_mount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/portfolio").json()
        response = client.post(
            "/risk/summary",
            params={"methodology": "FULL_REVALUATION"},
            json=book,
        )
        _assert_refused_inline(response)


def test_dashboard_refused_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        response = client.post("/api/v1/risk/dashboard")
        _assert_refused_inline(response)


def test_dashboard_refused_when_heavy_inline_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RISKFORGE_EXTERNAL_WORKER", raising=False)
    monkeypatch.setenv("RISKFORGE_HEAVY_INLINE", "0")
    with TestClient(app) as client:
        response = client.post("/risk/dashboard")
        _assert_refused_inline(response)


def test_heavy_inline_allowed_defaults_and_flags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RISKFORGE_EXTERNAL_WORKER", raising=False)
    monkeypatch.delenv("RISKFORGE_HEAVY_INLINE", raising=False)
    assert heavy_inline_allowed() is True
    assert RISK_RUNS_PATH == "/risk/runs"

    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    assert heavy_inline_allowed() is False

    monkeypatch.delenv("RISKFORGE_EXTERNAL_WORKER", raising=False)
    monkeypatch.setenv("RISKFORGE_HEAVY_INLINE", "0")
    assert heavy_inline_allowed() is False


@pytest.mark.parametrize("methodology", ["LINEAR", "DELTA_GAMMA"])
def test_interactive_summary_stays_sync_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
    methodology: str,
) -> None:
    monkeypatch.setenv("RISKFORGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        response = client.post(
            "/api/v1/risk/summary",
            params={"methodology": methodology},
            json=book,
        )
        assert response.status_code == 200, response.text
        assert response.json()["portfolio_id"] == book["id"]
