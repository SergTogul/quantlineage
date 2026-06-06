from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_full_dashboard_flow():
    with TestClient(app) as client:
        portfolio = client.get("/portfolio").json()
        summary = client.post("/risk/summary", json=portfolio)
        stress = client.post("/risk/stress", json=portfolio)
        contributors = client.post("/risk/contributors", json=portfolio)
        limits = client.post("/risk/limits", json=portfolio)
        assert summary.status_code == 200
        assert stress.status_code == 200
        assert contributors.status_code == 200
        assert limits.status_code == 200
        assert summary.json()["portfolio_id"] == portfolio["id"]
        assert len(stress.json()) >= 5
        assert len(contributors.json()) == len(portfolio["positions"])


def test_threat_scenario_evaluation_api():
    with TestClient(app) as client:
        portfolio = client.get("/portfolio").json()
        scenarios = client.get("/risk/stress/scenarios")
        report = client.post("/risk/stress/evaluate", json=portfolio)
        assert scenarios.status_code == 200
        body = scenarios.json()
        assert len(body) >= 5
        assert "shocks" in body[0] and "category" in body[0]
        assert report.status_code == 200
        payload = report.json()
        assert payload["portfolio_id"] == portfolio["id"]
        assert payload["evaluations"]
        assert payload["worst_scenario"] == payload["evaluations"][0]["scenario"]


def test_custom_stress_api_contract():
    with TestClient(app) as client:
        portfolio = client.get("/portfolio").json()
        payload = {
            "portfolio": portfolio,
            "scenarios": [{"name": "Custom", "equity_shock": -0.1, "max_loss_pct": 0.02}],
        }
        response = client.post("/risk/stress/evaluate/custom", json=payload)
        assert response.status_code == 200
        assert response.json()["evaluations"][0]["scenario"] == "Custom"
