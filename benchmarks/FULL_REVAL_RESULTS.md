# Stage 10.3 FULL_REVALUATION results

Host observations for the product FULL_REVALUATION / LINEAR / DELTA_GAMMA
paths on a seeded multi-asset fixture. **Not a host SLA. Not an HTTP SLA.**
Labeled-runner **SLA-K1/K2 unchanged / post-R0**.

## Non-claims

- Not an HTTP SLA. Not multi-tenant capacity. Not production throughput.
- Labeled-runner SLA-K1/K2 unchanged / post-R0; do not run the M6 kernel SLA checker here.
- Wall time, RSS, and scenarios/sec are recorded host observations, not floors.
- Synthetic fixture snapshot and seeded panel — not vendor market data.

## Quant contract

- Shock unit: EquitySpot relative return (`0.01` = +1%); EquityVol relative vol level.
- Sign: P&L = shocked PV − base PV; loss = −P&L.
- Base market: fixture snapshot `stage103-fixture`, not live marks.
- Reconciliation: P&L checksum; builtin vs QuantLib allclose rtol=0.002.
- Synthetic seeded panel — not vendor data. Methodology is not switched to look faster.

## Environment

- platform: `macOS-13.7.8-x86_64-i386-64bit`
- machine: `x86_64`
- python: `3.12.14` numpy `2.5.2` QuantLib `1.43`
- logical CPUs: 8; in-process worker_count=1
- note: In-process worker_count=1. QuantLib is process-serialized (ADR 007). Not an HTTP SLA; SLA-K1/K2 unchanged/post-R0.

## Coarse profile

Smoke (4×8) is too small for pricing to dominate: scenario/snapshot
construction can exceed the product reprice. At 100×250 (same seed/book
family) pricing is the bottleneck. Persistence is not in this harness (0 ms).
Timed cells use the product iterator (no second materialized snapshot list).
LINEAR/DELTA_GAMMA stay on `approximate_pnl_from_panel` — the native scenario
kernel is not swapped in to look faster. No product-code rewrite: C++ / API
pricing paths are out of this lane, and methodology is unchanged.

### Smoke 4×8

| Phase | ms |
|---|---:|
| scenario construction | 11.365 |
| snapshot transforms | 10.912 |
| engine construction | 0.011 |
| pricing (product path) | 4.550 |
| persistence | 0.000 |
| aggregation / checksum | 0.121 |

### 100×250 FULL_REVALUATION builtin (same fixture family)

| Phase | ms |
|---|---:|
| scenario construction | 19.739 |
| snapshot transforms | 163.853 |
| engine construction | 0.005 |
| pricing (product path) | 1477.0 |
| persistence | 0.000 |
| aggregation / checksum | 0.387 |

## Scaling table

| N trades | S scenarios | methodology | engine | status | wall_ms | wall_ms_warm | peak_rss_kib | scenarios/sec | workers | cache | checksum |
|---:|---:|---|---|---|---:|---:|---:|---:|---:|---|---|
| 100 | 250 | FULL_REVALUATION | builtin | ok | 1328.3 | 1062.6 | 43572.0 | 188.210 | 1 | valuation_lru_bypassed | `d13aee609b0076ac4ee7b75450c866b852bd176e67dba8f4d19284d76a7d4700` |
| 100 | 250 | FULL_REVALUATION | quantlib | ok | 2044.5 | 7230.7 | 68804.0 | 122.279 | 1 | valuation_lru_bypassed | `20ccc6d755b476d0cb6d9f20c8a59549fffcb943016343e9bb65879339b60b34` |
| 100 | 1000 | FULL_REVALUATION | builtin | ok | 6449.4 | 4661.1 | 47516.0 | 155.053 | 1 | valuation_lru_bypassed | `4da7204bdf2d75549bce3426c213cc0341bcad7581e352a99678e483e9153cca` |
| 100 | 1000 | FULL_REVALUATION | quantlib | ok | 18111.9 | 10273.5 | 72956.0 | 55.212 | 1 | valuation_lru_bypassed | `712a9d2875c15df0de88d7f90cd27750909a99710a87af497eed7702259bf134` |
| 1000 | 250 | FULL_REVALUATION | builtin | ok | 31858.7 | 31858.7 | 44736.0 | 7.847 | 1 | valuation_lru_bypassed | `c787c9b64212596991c9fcdd02674671bf7e59561ff75e9a55fe3d76db1dbb8e` |
| 1000 | 250 | FULL_REVALUATION | quantlib | ok | 25184.6 | 25184.6 | 71488.0 | 9.927 | 1 | valuation_lru_bypassed | `1ee92152e46d7101bac2531f31963aa02a7f823a1114fcd5f9e6da608bdeb4ae` |
| 1000 | 1000 | FULL_REVALUATION | builtin | ok | 46758.5 | 46758.5 | 49020.0 | 21.386 | 1 | valuation_lru_bypassed | `b21be9bc98f2fc206f56454507858e03484b93d9e399fe3157d163871961a13d` |
| 1000 | 1000 | FULL_REVALUATION | quantlib | ok | 116095.5 | 116095.5 | 75716.0 | 8.614 | 1 | valuation_lru_bypassed | `ac23b192d10b5e8197bbc9f84ad844d8a0e1fa53c8b64d32291fef8e36c6adb1` |
| 10000 | 1000 | LINEAR | builtin | ok | 18673.5 | 18673.5 | 140944.0 | 53.552 | 1 | greeks_once_at_base | `513ce5595351d66b75eb7ea970ef188ace5f673abd5147ce79d04dadd1884204` |
| 10000 | 1000 | DELTA_GAMMA | builtin | ok | 24812.4 | 24812.4 | 140880.0 | 40.302 | 1 | greeks_once_at_base | `5ad10b11729c6b6919caff40a3c29ee194efbda4d5f4ba9da7ffb58f8f8a3bb8` |

## Chart (generated from JSON)

Wall times below are copied from the JSON/CSV rows. Not hand-drawn.

- `100×250 FULL_REVALUATION builtin`: 1328.3 ms
- `100×250 FULL_REVALUATION quantlib`: 2044.5 ms
- `100×1000 FULL_REVALUATION builtin`: 6449.4 ms
- `100×1000 FULL_REVALUATION quantlib`: 18111.9 ms
- `1000×250 FULL_REVALUATION builtin`: 31858.7 ms
- `1000×250 FULL_REVALUATION quantlib`: 25184.6 ms
- `1000×1000 FULL_REVALUATION builtin`: 46758.5 ms
- `1000×1000 FULL_REVALUATION quantlib`: 116095.5 ms
- `10000×1000 LINEAR builtin`: 18673.5 ms
- `10000×1000 DELTA_GAMMA builtin`: 24812.4 ms

Warm vs cold is recorded when N×S ≤ 100×1000; larger cells record cold only
(same checksum path). QuantLib warm can be slower than cold on this host —
that is left as observed, not smoothed.

R0.6 identity benches in `run_full_reval_bench.py` are unchanged.
