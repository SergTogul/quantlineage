# QuantLineage rebrand review

## Repository

- old: `SergTogul/riskforge-mvp`
- new: `SergTogul/quantlineage`
- rename verified: **pending GitHub `gh repo rename` in this change** (filled after the remote rename)

Local origin at start of work: `https://github.com/SergTogul/riskforge-mvp.git`  
HEAD baseline: `e800a7bffc66278e7be62be62353b6d5be566d3f` (`master`)  
Branch: `rebrand/quantlineage`

## Search proof

Working-tree searches after the rename (excludes `.git/`, `node_modules/`, `backend/.venv/`, `dist/`):

```text
rg -n -i 'riskforge|risk[ _-]?forge' \
  --glob '!node_modules/**' --glob '!.git/**' \
  --glob '!backend/.venv/**' --glob '!dist/**' .
# no output; exit 1

rg -n 'riskforge-mvp' .
# no output; exit 1

find . \( -iname '*riskforge*' -o -iname '*risk*forge*' \) \
  ! -path './.git/*' ! -path '*/node_modules/*' ! -path '*/.venv/*'
# no output
```

Zero hits for `RiskForge`, `RISKFORGE`, `riskforge`, and `riskforge-mvp`.

The Playwright smoke test asserts the old wordmark is absent by joining `['RISK', 'FORGE']` so the source file itself does not contain a contiguous legacy brand token.

## Main renamed surfaces

| Surface | Result |
|---|---|
| README | Rewritten as QuantLineage product narrative |
| UI | Nav `QUANTLINEAGE`; subtitle `AI-Powered Multi-Asset Risk & Attribution Platform` |
| API title | `QuantLineage API` |
| npm package | `quantlineage-ui` (`package.json` + lockfile root `name`) |
| Python package | `quantlineage-backend` |
| Environment variables | every `RISKFORGE_*` → `QUANTLINEAGE_*` (no compatibility aliases) |
| Compose DB/user/volume | `quantlineage` / `quantlineage` / `quantlineage_pgdata` |
| MCP identity/config | `serverInfo.name` = `quantlineage`; `mcpServers.quantlineage` |
| Sample firm labels | `firm = "QuantLineage"` |
| Docs | `docs/**`, `AGENTS.md`, `BUILD_NOTES.md`, `ROADMAP.md`, reviews, ADRs |
| Tests | backend, frontend, E2E, CI pins |
| CI | `.github/workflows/ci.yml` and nightly use `QUANTLINEAGE_*` |
| Native ABI | `quantlineage_kernel_abi_version`, `quantlineage_portfolio_scenarios`, `quantlineage::` |
| Demo screenshots | `docs/demo/quantlineage_demo_0{1-4}_*.png` |

## UI polish completed

- **Sharpe unit:** Historical Analytics shows `—` (dimensionless), not the volatility unit.
- **Canonical Overview:** default remains `status`; README/demo describe status only; other layouts remain reachable by hash, not advertised as product features.
- **Hero risk-change action:** Overview status blotter links `Why did my risk change?` → `#var-es/risk-change`.
- **Copy cleanup:** user-meaning first; POST paths / nested-benchmark internals behind `<details>` or BlockHelp.
- **Collapsible API preview:** Scenario Builder payload is `<details><summary>API payload</summary>…`.
- **Chart formatting:** existing SVG charts gained formatted min/max, percent/currency units, first/last dates, and light y-axis labels.
- **Provenance/data-source identity:** backend `data_source_label` (e.g. `Synthetic replay · demo-multi-factor-history/v1` or `Public EOD · real:public:wave-a/<hash>`) displayed on Historical Analytics, Risk Change, and Risk Runs / provenance. Frontend does not infer source kind.

## Verification

| Command | Result |
|---|---|
| `PYTHONPATH=. QUANTLINEAGE_PRICING_ENGINE=builtin pytest -q` (backend) | **1850 passed**, 9 skipped, 1 warning in 122.38s |
| QuantLib hard-gate (`QUANTLINEAGE_PRICING_ENGINE=quantlib QUANTLINEAGE_REQUIRE_QUANTLIB=1` on the listed golden/adapter files) | **134 passed** in 5.06s (QuantLib 1.43) |
| `ruff check app tests` | All checks passed (import-order fix in `historical_analytics.py`) |
| `mypy app` (full project venv, mypy 1.20.2) | 263 pre-existing `union-attr` errors in 3 unchanged files (`snapshot_overlay.py`, `portfolio_service.py`, `result_payloads.py`). CI lint job installs `requirements-dev.txt` only. Not introduced by this rebrand. |
| `cd frontend && npm test` | **206 passed** (27 files) |
| `npm run lint` | pass (`--max-warnings 0`) |
| `npm run build` | pass (Vite 8.2.2) |
| `cd e2e && npm test` | **14 passed** in 1.3m, including QUANTLINEAGE visible, hero navigation, Sharpe `—`, collapsed API payload, Risk Query, RiskRun provenance |
| `docker compose down -v && docker compose up --build` | **Not run:** Docker daemon was not running (`Cannot connect to the Docker daemon at unix:///Users/user/.colima/default/docker.sock`). Compose files and `scripts/smoke_postgres.sh` use `quantlineage` identity; `tests/test_shared_compose.py` passed. CI `postgres-persistence-smoke` is the live gate. |

Fast baseline before edits: `tests/test_pricing.py tests/test_quant_properties.py` → 15 passed.

## Remaining references

None in the working tree.

Git history still contains the old name (not rewritten). The local checkout directory may still be named `riskforge-mvp`; that is a filesystem path, not a tracked file.

Local Compose from a clean volume was not exercised because the Docker daemon was down; GitHub Actions postgres-smoke / PR-FULL must confirm that path.
