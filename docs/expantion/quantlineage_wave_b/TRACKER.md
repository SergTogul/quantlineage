# Wave B Tracker

| ID | Task | Status | Evidence | Blocker |
|---|---|---|---|---|
| B0 | Inspect/reuse current analytics APIs | DONE | `B0_INTEGRATION_MAP.md`; commit `aebfafa` | |
| B1 | Historical analytics backend | DONE | commit `0d52457`; `tests/test_historical_analytics.py` 13 passed; review PASS `.superpowers/sdd/task-b1-review.md` | |
| G1 | Historical analytics gate | DONE | `aebfafa`..`cc27632`; review PASS; no Critical/Important | |
| B2 | Benchmark/relative risk | DONE | commit `497ee4a`; `tests/test_historical_analytics.py` 23 passed; review PASS `.superpowers/sdd/task-b2-review.md` | |
| G2 | Benchmark gate | DONE | `cc27632`..`6f52222`; review PASS; no Critical/Important | |
| B3 | Risk visualizations | DONE | commit `e02872b`; frontend 176 passed; review PASS `.superpowers/sdd/task-b3-review.md` | |
| G3 | Visualization gate | DONE | `6f52222`..`e02872b`; review PASS; no Critical/Important | |
| B4 | Risk-change waterfall | DONE | commit `60b0188`; frontend 182 passed; review PASS `.superpowers/sdd/task-b4-review.md` | |
| G4 | Risk-change gate | DONE | `e02872b`..`60b0188`; review PASS; no Critical/Important | |
| B5 | Historical Analytics UI | DONE | commit `0e43ba1`; frontend 192 passed; review PASS `.superpowers/sdd/task-b5-review.md` | |
| G5 | UI gate | DONE | `60b0188`..`0e43ba1`; review PASS; no Critical/Important | |
| B6 | Demo/polish/docs | IN_PROGRESS | `docs/historical_analytics_demo.md`; panel hashes `#var-es/contributors` `#var-es/risk-change` `#risk-factors/kr-dv01`; frontend 196 passed; G6 not marked DONE | |
| G6 | Demo gate | NOT_STARTED | | |
| B7 | Hostile review + full regression | NOT_STARTED | | |
| G7 | Wave B final gate | NOT_STARTED | | |

Overall: IN_PROGRESS (G1–G5 DONE, B6 IN_PROGRESS)
