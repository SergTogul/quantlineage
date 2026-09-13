# Optional public-data demo (Wave A)

RiskForge can freeze **public end-of-day** equity/ETF prints (Yahoo Finance public JSON)
and **public FRED** USD Treasury yields into the existing historical-dataset and
`MarketSnapshot` path. This is **not** an institutional vendor feed, not Bloomberg,
not Refinitiv, not streaming, and not a licensed entitlements plant.

Synthetic / packaged demo history remains the **default**. Public materialization is
explicit and optional. Compose and API startup must not require internet.

## Credentials

- Yahoo public JSON: none.
- FRED: `FRED_API_KEY` via environment only. Never commit, log, or put the key in
  API bodies, provenance, or the frontend.

## Default (synthetic)

Unset or:

```text
QUANTLINEAGE_DATA_MODE=synthetic
```

loads the packaged per-factor replay (`data/demo_multi_factor_history.csv`,
id `demo-multi-factor-history`). No Yahoo/FRED import or HTTP.

`RISKFORGE_HISTORICAL_DATASET` is unchanged. Do not rename it for Wave A.

`docker-compose.yml` does **not** set `QUANTLINEAGE_DATA_MODE=public`. Default
Compose / API lifespan starts on the demo CSV even if Yahoo/FRED are down.

## Freeze a public artifact

From the repo root (backend venv):

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/build_public_demo_data.py --live \
  --output data/public_history
```

`--live` is required for Yahoo/FRED HTTP. Without `--live` the command refuses to
fetch (CI/tests inject fakes). Do not commit a live Yahoo download.

Each freeze writes **content-hashed** files that are never overwritten by a later
pull with different bytes:

```text
data/public_history/real-public-wave-a/<sha256>.csv
data/public_history/real-public-wave-a/<sha256>.json
```

The script prints provider, source symbols, coverage, aligned observations,
dataset id/version/hash, snapshot id/as_of, and warnings. Dataset identity is:

```text
dataset_id      = real:public:wave-a
dataset_version = <sha256 of transformed panel>
```

`dataset_id` + `dataset_version` resolve those immutable bytes. Snapshot identity is
`real:public:wave-a:{as_of}:{snapshot_content_hash}` so a Yahoo/FRED revision of the
same calendar date cannot reuse a prior RiskRun snapshot id.

Then:

```text
QUANTLINEAGE_DATA_MODE=public
# optional pin to one frozen version:
# QUANTLINEAGE_PUBLIC_HISTORY_CSV=/abs/path/data/public_history/real-public-wave-a/<sha256>.csv
# QUANTLINEAGE_PUBLIC_HISTORY_DIR=/abs/path/data/public_history
```

If mode is `public` and the frozen CSV is missing, resolving the dataset **fails
closed** with a message pointing at `scripts/build_public_demo_data.py`. It does
not HTTP, hang, or fall back silently.

## Universe (Wave A)

Public-data mode currently covers US equity spot and USD Treasury-rate factors.
FX and volatility remain outside the public-data Wave A universe.

Supported public mappings: AAPL, MSFT, NVDA, SPY plus FRED DGS2 / DGS5 / DGS10.
The public snapshot builder attaches cash-book spots and USD key rates only. It
does **not** attach FX spots or vol surfaces. The existing cross-asset derivatives
demo book still uses packaged synthetic history unless you bind a public snapshot
that actually contains the marks that book needs.


## CI stays offline

CI and pytest never call live Yahoo or FRED. Adapters are injected fakes or
`httpx.MockTransport`. Default factory tests must not import those adapters.

## Market Data UI

In the frontend, open **Market Data** (`section=market-data`):

1. Search the curated Wave A universe (AAPL/MSFT/NVDA/SPY + DGS2/DGS5/DGS10).
2. Load history / inspect quality (API tables; the UI does not compute risk).
3. Freeze dataset and build snapshot via the API (`POST /api/v1/data/datasets`,
   `POST /api/v1/market/snapshots/from-public-data`).

The browser talks to the QuantLineage API only. It does not call Yahoo or FRED.

## T0 / T1 comparison

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/build_public_demo_data.py --live \
  --output data/public_history \
  --t0 YYYY-MM-DD --t1 YYYY-MM-DD
```

The script builds two G5 public snapshots and prints both ids/as_of plus
`source_observation_date` lineage (Monday `as_of` keeps Friday's last print).

It does **not** add a second compare engine. Persist two COMPLETED RiskRuns bound
to those snapshot ids, then use existing **Why did my risk change?**
(`POST /api/v1/risk/runs/compare` on Analytics).
