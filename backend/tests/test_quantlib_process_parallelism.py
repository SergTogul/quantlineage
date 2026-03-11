"""R0.3.5 — process-level QuantLib parallelism (RF-002 remaining slice).

Pins the bounded design in ADR 007:

- Compose ``worker`` is a distinct OS process from the API.
- In-process QuantLib stays serialized by ``_QL_PROCESS_LOCK``.
- ``full_revaluation_pnl_series`` does not spawn a thread/process pool.
- Native kernels do not reference QuantLib.
- A ``ThreadPoolExecutor`` that prices QuantLib without the process lock
  is a contract violation (detector + live tree scan).

Does not start a job platform or a full-reval ``ProcessPoolExecutor``.
"""

from __future__ import annotations

import ast
import inspect
import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

from tests.test_compose_loopback import COMPOSE_PATH, _iter_service_bodies

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
NATIVE_ROOT = BACKEND_ROOT / "native"
NATIVE_SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}

_POOL_NAMES = frozenset({"ThreadPoolExecutor", "ProcessPoolExecutor"})
_QL_DIRECT = re.compile(r"\bQuantLib\b|\bql\.Settings\b")
_PROCESS_LOCK = re.compile(r"_QL_PROCESS_LOCK|\._session\b|_session\(")
_QL_IN_NATIVE = re.compile(
    r"quantlib|<ql/|ql\.hpp|QuantLib::",
    re.IGNORECASE,
)

# Synthetic regression: must be reported as a violation.
_UNSAFE_QL_THREAD_POOL = """
from concurrent.futures import ThreadPoolExecutor
import QuantLib as ql

def _price() -> None:
    ql.Settings.instance().evaluationDate = ql.Date(2, 1, 2020)

with ThreadPoolExecutor(max_workers=2) as pool:
    pool.submit(_price)
"""

_SAFE_JOB_POOL = """
from concurrent.futures import ThreadPoolExecutor

def _schedule() -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        pool.submit(lambda: None)
"""

_SAFE_LOCKED_POOL = """
from concurrent.futures import ThreadPoolExecutor
import QuantLib as ql
from threading import RLock

_QL_PROCESS_LOCK = RLock()

def _price() -> None:
    with _QL_PROCESS_LOCK:
        ql.Settings.instance().evaluationDate = ql.Date(2, 1, 2020)

with ThreadPoolExecutor(max_workers=2) as pool:
    pool.submit(_price)
"""


def unlocked_ql_thread_pool_violations(
    source: str, *, filename: str = "<mem>"
) -> list[str]:
    """Fail closed if a thread/process pool prices QuantLib without the lock.

    A file is a violation when it:

    1. constructs or names ``ThreadPoolExecutor`` / ``ProcessPoolExecutor``,
    2. references QuantLib / ``ql.Settings`` directly, and
    3. does not mention ``_QL_PROCESS_LOCK`` or ``_session``.

    Job schedulers that never import QuantLib (``risk_run_worker``) are allowed.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [f"{filename}: unparsed Python; fail closed"]
    uses_pool = False
    for node in ast.walk(tree):
        if (isinstance(node, ast.Name) and node.id in _POOL_NAMES) or (
            isinstance(node, ast.Attribute) and node.attr in _POOL_NAMES
        ):
            uses_pool = True
    if not uses_pool:
        return []
    if _QL_DIRECT.search(source) is None:
        return []
    if _PROCESS_LOCK.search(source) is not None:
        return []
    return [
        f"{filename}: ThreadPoolExecutor/ProcessPoolExecutor prices QuantLib "
        "without _QL_PROCESS_LOCK / _session"
    ]


def _iter_app_python_files() -> list[Path]:
    return sorted(
        path
        for path in APP_ROOT.rglob("*.py")
        if path.is_file() and ".__pycache__" not in path.parts
    )


def test_detector_flags_thread_pool_that_prices_quantlib_without_lock():
    hits = unlocked_ql_thread_pool_violations(
        _UNSAFE_QL_THREAD_POOL, filename="unsafe.py"
    )
    assert hits, (
        "detector must fail a ThreadPoolExecutor that mutates ql.Settings "
        "without _QL_PROCESS_LOCK"
    )


def test_detector_allows_job_pool_that_does_not_import_quantlib():
    assert unlocked_ql_thread_pool_violations(_SAFE_JOB_POOL) == []


def test_detector_allows_thread_pool_that_takes_process_lock():
    assert unlocked_ql_thread_pool_violations(_SAFE_LOCKED_POOL) == []


def test_app_has_no_unlocked_quantlib_thread_pool():
    violations: list[str] = []
    for path in _iter_app_python_files():
        violations.extend(
            unlocked_ql_thread_pool_violations(
                path.read_text(encoding="utf-8"),
                filename=str(path.relative_to(BACKEND_ROOT)),
            )
        )
    assert violations == []


def test_risk_run_worker_job_pool_does_not_import_quantlib():
    """In-process executor is a job scheduler; QL stays behind PricingEngine."""
    from app.services import risk_run_worker

    source = inspect.getsource(risk_run_worker)
    assert "ThreadPoolExecutor" in source
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    assert "QuantLib" not in imported
    assert "ql" not in imported


def test_full_revaluation_pnl_series_has_no_executor_pool():
    from app.risk.historical import full_revaluation_pnl_series

    source = inspect.getsource(full_revaluation_pnl_series)
    assert "ThreadPoolExecutor" not in source
    assert "ProcessPoolExecutor" not in source
    hits = unlocked_ql_thread_pool_violations(source, filename="historical.py")
    assert hits == []


def test_compose_worker_is_distinct_process_from_api():
    """Compose backend defers; worker runs ``python -m app.worker``."""
    text = COMPOSE_PATH.read_text(encoding="utf-8")
    bodies = _iter_service_bodies(text)
    assert bodies is not None
    assert "backend" in bodies
    assert "worker" in bodies
    backend = "\n".join(bodies["backend"])
    worker = "\n".join(bodies["worker"])
    assert "RISKFORGE_EXTERNAL_WORKER" in backend
    assert re.search(r'python",\s*"-m",\s*"app\.worker"', worker) or (
        "python -m app.worker" in worker
    )
    assert "RISKFORGE_EXTERNAL_WORKER" not in worker
    assert "app.worker" not in backend
    assert "app.main" not in worker


def test_worker_module_is_not_the_api_process():
    from app import main, worker

    assert Path(worker.__file__).resolve() != Path(main.__file__).resolve()
    assert hasattr(main, "app")
    assert not hasattr(worker, "app")
    assert callable(worker.main)
    assert "python -m app.worker" in (worker.__doc__ or "")


def test_native_sources_do_not_reference_quantlib():
    hits: list[str] = []
    for path in sorted(NATIVE_ROOT.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in NATIVE_SOURCE_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        if _QL_IN_NATIVE.search(text):
            hits.append(str(path.relative_to(REPO_ROOT)))
    assert hits == [], f"native kernel must stay QuantLib-free: {hits}"


def test_sibling_processes_isolate_quantlib_settings():
    """Two OS children can hold different evaluation dates concurrently."""
    from tests.quantlib_gate import import_quantlib

    import_quantlib()
    child = (
        "import os, sys\n"
        "from datetime import date\n"
        "import QuantLib as ql\n"
        "iso = sys.argv[1]\n"
        "d = date.fromisoformat(iso)\n"
        "ql.Settings.instance().evaluationDate = ql.Date(d.day, d.month, d.year)\n"
        "obs = ql.Settings.instance().evaluationDate\n"
        "sys.stdout.write(f'{os.getpid()} {obs.year()} {obs.month()} {obs.dayOfMonth()}\\n')\n"
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}
    dates = ("2020-01-02", "2024-06-14")
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", child, iso],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        for iso in dates
    ]
    parsed: list[tuple[int, tuple[int, int, int]]] = []
    for proc in procs:
        out, err = proc.communicate(timeout=30)
        assert proc.returncode == 0, err
        pid_s, year_s, month_s, day_s = out.strip().split()
        parsed.append((int(pid_s), (int(year_s), int(month_s), int(day_s))))
    assert parsed[0][0] != parsed[1][0]
    assert parsed[0][0] != os.getpid()
    assert parsed[1][0] != os.getpid()
    assert {item[1] for item in parsed} == {(2020, 1, 2), (2024, 6, 14)}


def test_thread_pool_value_calls_remain_serialized_by_process_lock():
    """Job-style ThreadPoolExecutor must still take ``_QL_PROCESS_LOCK``."""
    from tests.quantlib_gate import import_quantlib

    ql = import_quantlib()
    from app.domain.models import BondPosition, MarketSnapshot
    from app.pricing.quantlib import QuantLibPricingEngine

    engine = QuantLibPricingEngine(evaluation_date=date(2020, 1, 2))
    bond = BondPosition(
        type="bond",
        id="zc",
        issuer="UST",
        face_value=1_000_000,
        quantity=1,
        maturity_years=10.0,
        yield_rate=0.04,
        duration=8.0,
    )
    observed: list = []
    observed_lock = threading.Lock()
    original_bond = engine._bond

    def spy_bond(position, market=None):
        with observed_lock:
            observed.append(ql.Settings.instance().evaluationDate)
        return original_bond(position, market)

    engine._bond = spy_bond

    def price(as_of: str) -> None:
        engine.value(bond, MarketSnapshot(id=as_of, as_of=as_of, rates={"USD": 0.04}))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(price, "2018-01-01"),
            pool.submit(price, "2024-06-14"),
        ]
        for future in futures:
            future.result(timeout=30)

    assert len(observed) == 2
    expected = {
        engine._ql_date(date(2018, 1, 1)),
        engine._ql_date(date(2024, 6, 14)),
    }
    assert set(observed) == expected
