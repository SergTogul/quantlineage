"""R0.10.2 / RF-015: one dashboard batch POST instead of nine overlapping risk POSTs."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.execution_class import ExecutionClass, classify
from app.main import app

DASHBOARD_KEYS = {
    "portfolio",
    "summary",
    "stress",
    "threats",
    "contributors",
    "limits",
    "factors",
    "varReport",
    "hierarchy",
    "attribution",
}


def test_dashboard_batch_route_returns_payload_keys() -> None:
    """Live app: one POST yields the dashboard keys the UI already consumes."""
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio")
        assert book.status_code == 200
        portfolio = book.json()

        response = client.post("/api/v1/risk/dashboard", json=portfolio)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert set(payload) == DASHBOARD_KEYS
        assert payload["portfolio"]["id"] == portfolio["id"]
        assert payload["summary"]["portfolio_id"] == portfolio["id"]
        assert payload["varReport"]["portfolio_id"] == portfolio["id"]
        assert isinstance(payload["stress"], list)
        assert payload["stress"]
        assert isinstance(payload["threats"], dict)
        assert payload["threats"].get("evaluations")
        assert isinstance(payload["contributors"], list)
        assert len(payload["contributors"]) == len(portfolio["positions"])
        assert isinstance(payload["limits"], list)
        assert payload["limits"]
        assert isinstance(payload["factors"], list)
        assert payload["factors"]
        assert isinstance(payload["hierarchy"], dict)
        assert payload["hierarchy"].get("name")
        assert isinstance(payload["attribution"], dict)
        assert "total_change" in payload["attribution"]


def test_dashboard_batch_dual_mount_and_default_book() -> None:
    """Legacy mount and empty body both resolve the default demo book."""
    with TestClient(app) as client:
        default_id = client.get("/portfolio").json()["id"]

        empty = client.post("/api/v1/risk/dashboard")
        assert empty.status_code == 200, empty.text
        assert empty.json()["portfolio"]["id"] == default_id

        legacy = client.post("/risk/dashboard")
        assert legacy.status_code == 200, legacy.text
        assert set(legacy.json()) == DASHBOARD_KEYS
        assert legacy.json()["portfolio"]["id"] == default_id


def test_dashboard_batch_is_heavy() -> None:
    """Hierarchy + VaR + evaluate in one request is HEAVY (R0.10.1 map)."""
    assert classify("POST", "/risk/dashboard") is ExecutionClass.HEAVY
    assert classify("POST", "/api/v1/risk/dashboard") is ExecutionClass.HEAVY
