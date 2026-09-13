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
| B6 | Demo/polish/docs | DONE | commit `fab0357`; `docs/historical_analytics_demo.md`; frontend 195 passed (independent); review PASS `.superpowers/sdd/task-b6-review.md` | |
| G6 | Demo gate | DONE | `0e43ba1`..`fab0357`; review PASS; no Critical/Important | |
| B7 | Hostile review + full regression | IN_PROGRESS | `reviews/wave-b-analytics-hostile-review.md`; stale-HA keyed display; backend 1778 passed / frontend 198 passed + lint; G7 not marked DONE | |
| G7 | Wave B final gate | NOT_STARTED | | |

Overall: IN_PROGRESS (G1–G6 DONE, B7 IN_PROGRESS)
