# Public data sources (Wave A)

RiskForge Wave A can ingest **public end-of-day equity/ETF history** and **public FRED
macro/rates series**. This is not a licensed market-data vendor plant, not a real-time
feed, and not institutional entitlements infrastructure.

Adapters live in `backend/app/market/ingestion/`. Pricing and risk code must not call
them. HTTP is injected (`httpx.Client`) so CI stays offline.

## Selection (locked)

| Role | Provider | Access | Credentials |
|---|---|---|---|
| Equity/ETF search + daily adjusted history | Yahoo Finance public JSON (`query1.finance.yahoo.com`) | Unofficial public EOD/search | None |
| USD rates/macro | FRED REST (`api.stlouisfed.org`) | Official public series | `FRED_API_KEY` environment only |

## Yahoo Finance (public JSON)

- **Access model:** Unauthenticated HTTP JSON. Search `GET /v1/finance/search?q=`. Daily
  chart `GET /v8/finance/chart/{symbol}` with `interval=1d` and `includeAdjustedClose=true`.
- **History support:** Daily bars only in Wave A (`Frequency.DAILY`). Not ticks, not
  intraday, not a corporate-actions master.
- **Adjusted-price semantics:** History uses chart `indicators.adjclose` (split/dividend
  adjusted close), **not** raw `close`. Normalized series set `unit="price"` and
  `adjustment="adjusted"`. Relative returns for risk factors are a later transform
  (not done in the adapter).
- **Rate limits:** Yahoo does not publish a contractual quota. HTTP 429 is mapped to
  `rate_limited` and is **not** retried. Transient 5xx/timeout retry at most twice.
- **Credentials:** None. Do not add cookies, unofficial tokens, or scraped HTML.
- **Legal / public-use:** Public web JSON used for research/demo ingestion. Redistribution
  rights, SLA, symbology, and corporate-action completeness are **not** claimed. Do not
  describe this as Bloomberg, Refinitiv, or a paid EOD vendor.
- **Testability:** All CI tests use `httpx.MockTransport` fixtures. No live Yahoo calls
  in CI.

## FRED (official public REST)

- **Access model:** Official St. Louis Fed API. Observations
  `GET /fred/series/observations` with `series_id`, `file_type=json`, and `api_key`.
- **History support:** Daily (business-day) observations for series such as `DGS10`.
  Missing observations are the token `"."` and are **gaps**, never coerced to `0`.
- **Units:** DGS-style (and the Wave A FRED adapter default) are **percent levels**
  (`unit="percent"`). Example: `4.25` means 4.25%, not `0.0425`. Conversion to snapshot
  decimal rates or historical basis-point moves happens later, once, at freeze
  (AD-A10). The adapter does not convert.
- **Rate limits:** FRED publishes API usage limits. HTTP 429 → `rate_limited` with no
  retry loop. 5xx/timeout: at most two retries.
- **Credentials:** `FRED_API_KEY` via environment or explicit constructor argument.
  Never hardcoded, never logged, never placed in exception messages, provenance, or
  frontend payloads. Query parameter `api_key` is redacted from error text.
- **Legal / public-use:** FRED series are public U.S. government statistical releases
  subject to FRED terms of use. This is still **public data**, not a paid terminal.
- **Testability:** Fixture JSON + MockTransport. CI does not call `api.stlouisfed.org`.

## Quality, stale rule, and content hash

Validation, alignment, and hashing live in `backend/app/market/quality/` (no FastAPI,
no QuantLib/risk imports). `DataQualitySummary` from ingestion is reused.

- **Stale:** `STALE_AFTER_DAYS = 7` calendar days in `app.market.ingestion.normalize`.
  `is_stale` compares last observation to `requested_end` (or `retrieved_at.date()` when
  the request end is in the future). Exactly 7 days is not stale; 8 days is.
- **Minimum observations:** library default `MIN_OBSERVATIONS = 5`. Alignment uses the
  same floor unless the caller passes a higher `min_aligned` / `min_observations`.
- **Units:** Wave A allows only `price` and `percent`. Non-positive values fail only
  when `unit == "price"`. Missing FRED `"."` tokens stay gaps (`missing_count`); no
  interpolation.
- **Alignment:** date intersection of required series, no forward-fill, dropped dates
  reported per series, factor order sorted by `instrument_id`.
- **Content hash:** SHA-256 hex of canonical JSON (`sort_keys`, compact separators).
  Payload includes identity, unit, frequency, currency, adjustment,
  `normalization_version`, ordered `(date, value)` points, and `transform_config` when
  provided. **`retrieved_at` is excluded.**
- **Inspect API:** `GET /api/v1/instruments/{instrument_id}/quality?start=YYYY-MM-DD&end=YYYY-MM-DD`
  (dual-mounted). Curated catalog 404s unknown ids. Tests inject fake providers; no live
  Yahoo/FRED in CI.

## Honest non-claims

- Not a vendor market-data platform, not streaming, not a global security master.
- Public EOD gaps, delays, and unofficial Yahoo availability are expected.
- A RiskRun must consume **frozen** `HistoricalDataset` / `MarketSnapshot` identities,
  not live adapter responses (AD-A2, AD-A4).
