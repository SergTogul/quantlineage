"""RF-018: committed frontend OpenAPI snapshot stays aligned with app.openapi()."""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO_ROOT / "frontend" / "src" / "contracts" / "openapi-scenario.json"

SCENARIO_POST_PATHS = (
    "/api/v1/risk/stress/formal/evaluate/custom",
    "/api/v1/risk/stress/formal/compare",
    "/api/v1/risk/stress/reverse/multi",
)

SNAPSHOT_SCHEMAS = (
    "FactorShockWire",
    "ScenarioWire",
    "FormalCustomStressRequest",
    "FormalScenarioComparisonRequest",
    "MultiFactorReverseStressRequest",
)


def scenario_contract_from_openapi(spec: dict) -> dict:
    paths = spec["paths"]
    schemas = spec.get("components", {}).get("schemas", {})
    return {
        "openapi": spec.get("openapi"),
        "info": {"title": spec.get("info", {}).get("title"), "version": spec.get("info", {}).get("version")},
        "paths": {path: {"post": paths[path]["post"]} for path in SCENARIO_POST_PATHS},
        "components": {"schemas": {name: schemas[name] for name in SNAPSHOT_SCHEMAS}},
    }


def test_frontend_scenario_openapi_snapshot_exists():
    assert SNAPSHOT.is_file(), f"missing OpenAPI snapshot at {SNAPSHOT}"


def test_frontend_scenario_openapi_snapshot_matches_app():
    live = scenario_contract_from_openapi(app.openapi())
    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert snapshot["paths"].keys() == live["paths"].keys()
    for path in SCENARIO_POST_PATHS:
        live_ref = live["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]
        snap_ref = snapshot["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]
        assert snap_ref == live_ref, path
    for name in SNAPSHOT_SCHEMAS:
        assert snapshot["components"]["schemas"][name] == live["components"]["schemas"][name], name
    amount = snapshot["components"]["schemas"]["FactorShockWire"]["properties"]["amount"]["description"]
    assert "relative" in amount.lower()
    assert "0.0001" in amount
