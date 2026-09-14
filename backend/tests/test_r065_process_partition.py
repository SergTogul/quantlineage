"""R0.6.5 — HEAVY full-reval process partition is RiskRun / Compose worker.

Option B: do not add unused multiprocessing. QuantLib ``Settings`` is
process-owned (RF-002). FULL_REVALUATION summary/var is HEAVY and refused
on the request thread when the gate is on (``details.use=/risk/runs``).
R0.6.1 checksum is identity scaling evidence, not an SLA.
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.market_fixtures import FixedMarketProvider, equity_spot_market
from tests.test_compose_loopback import COMPOSE_PATH, _iter_service_bodies
from tests.test_full_reval_bench import BENCH_PATH, EXPECTED_CHECKSUM, IMPL, N_OBS

from app.api.backpressure import RISK_RUNS_PATH
from app.api.execution_class import ExecutionClass, classify
from app.domain.models import EquityPosition, Portfolio, RiskRunStatus, VaRMethodology
from app.main import app
from app.pricing.factory import create_pricing_engine
from app.risk.historical import HistoricalRiskEngine, full_revaluation_pnl_series
from app.services.portfolio_service import PortfolioService
from app.services.risk_run_worker import execute_run_type

PUBLIC_BAD_REQUEST = "Invalid request"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
_POOL_NAMES = frozenset({"ThreadPoolExecutor", "ProcessPoolExecutor"})
_MP_IMPORT = re.compile(r"\b(multiprocessing|ProcessPoolExecutor|concurrent\.futures)\b")

_FULL_REVAL_SYNC_PATHS = (
    ("/api/v1/risk/summary", {"methodology": "FULL_REVALUATION"}),
    ("/risk/summary", {"methodology": "FULL_REVALUATION"}),
    ("/api/v1/risk/var", {"methodology": "FULL_REVALUATION"}),
    ("/risk/var", {"methodology": "FULL_REVALUATION"}),
)


def _assert_refused_inline(response) -> None:
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "bad_request"
    assert body["message"] == PUBLIC_BAD_REQUEST
    assert isinstance(body["details"], dict)
    assert body["details"]["use"] == RISK_RUNS_PATH
    assert body["details"]["use"] == "/risk/runs"


def test_full_revaluation_summary_and_var_are_heavy() -> None:
    assert classify("POST", "/risk/summary", methodology="FULL_REVALUATION") is ExecutionClass.HEAVY
    assert classify("POST", "/risk/var", methodology="FULL_REVALUATION") is ExecutionClass.HEAVY
    assert classify("POST", "/api/v1/risk/summary", methodology=VaRMethodology.FULL_REVALUATION) is ExecutionClass.HEAVY
    assert classify("POST", "/api/v1/risk/var", methodology="FULL_REVALUATION") is ExecutionClass.HEAVY
    assert classify("POST", "/risk/summary") is ExecutionClass.INTERACTIVE
    assert classify("POST", "/risk/var") is ExecutionClass.HEAVY


@pytest.mark.parametrize("path,params", _FULL_REVAL_SYNC_PATHS)
def test_full_revaluation_summary_and_var_refused_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    params: dict[str, str],
) -> None:
    monkeypatch.setenv("QUANTLINEAGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        response = client.post(path, params=params, json=book)
        _assert_refused_inline(response)


@pytest.mark.parametrize("path,params", _FULL_REVAL_SYNC_PATHS)
def test_full_revaluation_summary_and_var_refused_when_heavy_inline_disabled(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    params: dict[str, str],
) -> None:
    monkeypatch.delenv("QUANTLINEAGE_EXTERNAL_WORKER", raising=False)
    monkeypatch.setenv("QUANTLINEAGE_HEAVY_INLINE", "0")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        response = client.post(path, params=params, json=book)
        _assert_refused_inline(response)


@pytest.mark.parametrize("run_type", ["summary", "var"])
def test_full_revaluation_risk_run_stays_queued_when_external_worker(
    monkeypatch: pytest.MonkeyPatch,
    run_type: str,
) -> None:
    """Gate-on HTTP does not price FULL_REVALUATION; RiskRun is the partition."""
    monkeypatch.setenv("QUANTLINEAGE_EXTERNAL_WORKER", "1")
    with TestClient(app) as client:
        book = client.get("/api/v1/portfolio").json()
        created = client.post(
            "/api/v1/risk/runs",
            json={
                "portfolio": book,
                "run_type": run_type,
                "request": {"methodology": "FULL_REVALUATION"},
            },
        )
        assert created.status_code == 202, created.text
        body = created.json()
        assert body["status"] == RiskRunStatus.QUEUED.value
        assert body["run_type"] == run_type
        assert body["results"] == []
        polled = client.get(f"/api/v1/risk/runs/{body['id']}")
        assert polled.status_code == 200, polled.text
        assert polled.json()["status"] == RiskRunStatus.QUEUED.value


def test_full_revaluation_execute_run_type_still_computes() -> None:
    """Worker dispatch (not the request thread) may run FULL_REVALUATION."""
    book = Portfolio(
        id="r065-book",
        name="R065",
        positions=[EquityPosition(type="equity", id="eq-1", symbol="NVDA", quantity=10)],
    )
    svc = PortfolioService(
        create_pricing_engine(),
        HistoricalRiskEngine(observations=8),
        market_data=FixedMarketProvider(equity_spot_market("NVDA", 190.0)),
    )
    for run_type in ("summary", "var"):
        payload = execute_run_type(
            svc,
            run_type=run_type,
            portfolio=book,
            request={"methodology": "FULL_REVALUATION"},
        )
        assert isinstance(payload, dict)
        assert payload.get("methodology") == "FULL_REVALUATION"


def test_r061_checksum_is_identity_scaling_evidence_not_sla() -> None:
    text = BENCH_PATH.read_text(encoding="utf-8")
    assert EXPECTED_CHECKSUM == "6602fa6906f2579f5c89af72a41ab274c07650234fff69387bc2202b5a40534f"
    assert EXPECTED_CHECKSUM in text
    assert IMPL in text
    assert str(N_OBS) in text
    assert "full_revaluation_pnl_series" in text
    assert not re.search(r"throughput\s*>\s*0", text)
    assert not re.search(r"(?m)^\s*(import |from ).*check_m6_sla", text)
    assert not re.search(r"check_m6_sla\.py\s", text)


def test_full_revaluation_pnl_series_has_no_process_or_thread_pool() -> None:
    source = inspect.getsource(full_revaluation_pnl_series)
    assert "ThreadPoolExecutor" not in source
    assert "ProcessPoolExecutor" not in source
    assert "multiprocessing" not in source


def test_full_reval_modules_do_not_start_unused_multiprocessing() -> None:
    """R0.6.5 option B: no unused scenario-block process pool."""
    relative = (
        "risk/historical.py",
        "risk/var.py",
        "services/risk_run_worker.py",
        "api/backpressure.py",
        "api/risk.py",
    )
    for rel in relative:
        path = APP_ROOT / rel
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        assert "multiprocessing" not in imported, rel
        pool_names = {
            node.attr if isinstance(node, ast.Attribute) else node.id
            for node in ast.walk(tree)
            if (isinstance(node, ast.Name) and node.id in _POOL_NAMES)
            or (isinstance(node, ast.Attribute) and node.attr in _POOL_NAMES)
        }
        if rel == "services/risk_run_worker.py":
            assert pool_names == {"ThreadPoolExecutor"}
            continue
        assert not pool_names, f"{rel} must not construct a pool: {pool_names}"


def test_worker_does_not_defer_unused_process_pool_to_r065() -> None:
    from app.services import risk_run_worker

    source = inspect.getsource(risk_run_worker)
    assert "ProcessPoolExecutor" in source
    assert "does not start a" in source
    assert "R0.6.5 may add" not in source


def test_compose_worker_is_the_full_reval_process_partition() -> None:
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    bodies = _iter_service_bodies(text)
    assert bodies is not None
    backend = "\n".join(bodies["backend"])
    worker = "\n".join(bodies["worker"])
    assert "QUANTLINEAGE_EXTERNAL_WORKER" in backend
    assert re.search(r'python",\s*"-m",\s*"app\.worker"', worker) or "python -m app.worker" in worker
    assert "QUANTLINEAGE_EXTERNAL_WORKER" not in worker
    assert "app.worker" not in backend
    assert _MP_IMPORT.search(inspect.getsource(full_revaluation_pnl_series)) is None
