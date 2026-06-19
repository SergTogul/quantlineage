"""Deterministic demo risk artifacts (M10.3).

Loads M10.1 demo portfolios and the production per-factor historical panel,
then runs summary VaR + default stress through ``PortfolioService``. Numbers
come only from deterministic engines — no live market vendors, no LLM math.

Default pricing adapter for artifact stability is **builtin** (override with
``RISKFORGE_PRICING_ENGINE``). Historical source is the per-factor demo panel
unless ``--dataset`` / ``RISKFORGE_HISTORICAL_DATASET`` is overridden. The
four-macro CSV remains available as ``--dataset demo``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.domain.models import VaRMethodology
from app.pricing.builtin import BuiltinPricingEngine
from app.pricing.factory import create_pricing_engine
from app.risk.stress import DEFAULT_SCENARIOS
from app.sample import DEMO_PORTFOLIOS, get_demo_portfolio
from app.services.portfolio_service import PortfolioService
from app.services.risk_factories import build_historical_risk_engine, dataset_identity

DEMO_ARTIFACT_SCHEMA_VERSION = 1
DEMO_ARTIFACT_ID = "demo-risk-artifact"
# Round PnL/risk floats so macOS vs Linux ULP noise does not break golden JSON.
# 8 dp absorbs ~1e-11 platform drift seen on GHA while keeping sub-cent demo precision.
DEMO_ARTIFACT_FLOAT_DECIMALS = 8


def _repo_root() -> Path:
    # backend/app/demo/run_demo_risk.py → parents[3] = repo root
    return Path(__file__).resolve().parents[3]


def default_artifact_path() -> Path:
    """Default write path under repo ``data/`` (not committed; generated on demand)."""
    return _repo_root() / "data" / "demo_risk_artifact.json"


def _pricing_engine_name() -> str:
    return os.getenv("RISKFORGE_PRICING_ENGINE", "builtin").strip().lower() or "builtin"


def _make_pricing(*, prefer_builtin: bool = True):
    """Build pricing engine; default builtin for cross-machine artifact parity."""
    if prefer_builtin and _pricing_engine_name() == "builtin":
        return BuiltinPricingEngine(), "builtin"
    name = _pricing_engine_name()
    return create_pricing_engine(), name


def build_demo_risk_artifact(
    *,
    portfolio_ids: list[str] | None = None,
    dataset_source: str | None = None,
    methodology: VaRMethodology = VaRMethodology.DELTA_GAMMA,
    prefer_builtin: bool = True,
) -> dict[str, Any]:
    """Compute a JSON-serializable demo risk artifact (deterministic for fixed inputs).

    Parameters
    ----------
    portfolio_ids:
        Subset of demo catalog ids; default is all ``DEMO_PORTFOLIOS`` in catalog order.
    dataset_source:
        Passed to ``create_historical_dataset`` (``demo`` / ``synthetic`` / CSV path
        / ``demo-multi-factor-history``). ``None`` → production per-factor demo panel.
    methodology:
        VaR methodology for summary / var_report.
    prefer_builtin:
        When True and env pricing is ``builtin`` (default), use ``BuiltinPricingEngine``
        without cache wrapper for stable dumps.
    """
    # Native kernel can change float paths; keep demo scripts on Python reference.
    os.environ.setdefault("RISKFORGE_SCENARIO_KERNEL", "python")

    if dataset_source is None:
        risk = build_historical_risk_engine()
        dataset_label, _ = dataset_identity(risk.dataset)
    else:
        risk = build_historical_risk_engine(historical_dataset_id=dataset_source)
        dataset_label, _ = dataset_identity(risk.dataset)

    pricing, pricing_name = _make_pricing(prefer_builtin=prefer_builtin)
    service = PortfolioService(pricing, risk)

    if portfolio_ids is None:
        portfolios = list(DEMO_PORTFOLIOS)
    else:
        portfolios = []
        for pid in portfolio_ids:
            found = get_demo_portfolio(pid)
            if found is None:
                raise ValueError(
                    f"unknown demo portfolio id: {pid!r}; "
                    f"known: {[p.id for p in DEMO_PORTFOLIOS]}"
                )
            portfolios.append(found)

    books: list[dict[str, Any]] = []
    for portfolio in portfolios:
        summary = service.summary(portfolio, methodology=methodology)
        var_report = service.var_report(portfolio, methodology=methodology)
        stresses = service.stresses(portfolio, list(DEFAULT_SCENARIOS))
        books.append(
            {
                "id": portfolio.id,
                "name": portfolio.name,
                "desk": portfolio.desk,
                "strategy": portfolio.strategy,
                "position_count": len(portfolio.positions),
                "summary": summary.model_dump(mode="json"),
                "var_report": {
                    "portfolio_id": var_report.portfolio_id,
                    "methodology": var_report.methodology.value
                    if hasattr(var_report.methodology, "value")
                    else str(var_report.methodology),
                    "methods": [m.model_dump(mode="json") for m in var_report.methods],
                    # Contributions omitted from default artifact (size); available via API.
                },
                "stress": [
                    {
                        "scenario": s.scenario,
                        "pnl": s.pnl,
                        # by_position omitted from default artifact (size).
                    }
                    for s in stresses
                ],
            }
        )

    return {
        "schema_version": DEMO_ARTIFACT_SCHEMA_VERSION,
        "artifact_id": DEMO_ARTIFACT_ID,
        "milestone": "M10.3",
        "pricing_engine": pricing_name,
        "historical_dataset": dataset_label,
        "methodology": methodology.value
        if hasattr(methodology, "value")
        else str(methodology),
        "scenario_set": [s.id or s.name for s in DEFAULT_SCENARIOS],
        "portfolios": books,
    }


def _stabilize_floats(value: Any, *, ndigits: int = DEMO_ARTIFACT_FLOAT_DECIMALS) -> Any:
    """Round floats for cross-platform dump parity; leave structure/types otherwise."""
    if isinstance(value, float):
        return round(value, ndigits)
    if isinstance(value, dict):
        return {k: _stabilize_floats(v, ndigits=ndigits) for k, v in value.items()}
    if isinstance(value, list):
        return [_stabilize_floats(v, ndigits=ndigits) for v in value]
    return value


def dumps_demo_artifact(artifact: dict[str, Any]) -> str:
    """Stable JSON text (sorted keys, rounded floats, trailing newline).

    Float rounding absorbs sub-1e-8 platform ULP drift so committed golden
    artifacts match across macOS/Linux for the same builtin + Python kernel.
    """
    stable = _stabilize_floats(artifact)
    return json.dumps(stable, sort_keys=True, indent=2, allow_nan=False) + "\n"


def run_demo_risk(
    *,
    output: Path | None = None,
    portfolio_ids: list[str] | None = None,
    dataset_source: str | None = None,
    check: bool = False,
) -> dict[str, Any]:
    """Build artifact; optionally write ``output`` and/or verify double-run equality."""
    artifact = build_demo_risk_artifact(
        portfolio_ids=portfolio_ids,
        dataset_source=dataset_source,
    )
    text = dumps_demo_artifact(artifact)
    if check:
        again = dumps_demo_artifact(
            build_demo_risk_artifact(
                portfolio_ids=portfolio_ids,
                dataset_source=dataset_source,
            )
        )
        if text != again:
            raise RuntimeError("demo risk artifact is not deterministic across re-runs")
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "M10.3: emit deterministic VaR/stress JSON for demo portfolios + "
            "demo historical factors (no live vendors)."
        )
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help=f"Write JSON artifact (default stdout; suggested: {default_artifact_path()})",
    )
    parser.add_argument(
        "--portfolio",
        action="append",
        dest="portfolios",
        metavar="ID",
        help="Demo portfolio id (repeatable). Default: all three themes.",
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="Historical source: demo-multi-factor-history|demo|synthetic|/path.csv "
        "(default: production per-factor demo panel).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if two consecutive builds are not byte-identical.",
    )
    args = parser.parse_args(argv)

    # Default CLI pricing to builtin unless caller already set the env.
    os.environ.setdefault("RISKFORGE_PRICING_ENGINE", "builtin")
    os.environ.setdefault("RISKFORGE_SCENARIO_KERNEL", "python")

    artifact = run_demo_risk(
        output=args.output,
        portfolio_ids=args.portfolios,
        dataset_source=args.dataset,
        check=args.check,
    )
    if args.output is None:
        sys.stdout.write(dumps_demo_artifact(artifact))
    else:
        print(f"wrote {args.output.resolve()}", file=sys.stderr)
        print(
            f"portfolios={len(artifact['portfolios'])} "
            f"pricing={artifact['pricing_engine']} "
            f"dataset={artifact['historical_dataset']}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
