# Wave C Tracker

| ID | Task | Status | Evidence | Blocker |
|---|---|---|---|---|
| C0 | Inventory deterministic services | DONE | `C0_INTEGRATION_MAP.md`; RF-019 `query.py` + Wave A catalog/history/quality + Wave B compare/KR-DV01/historical-analytics mapped; no MCP | |
| C1 | Tool schemas/service mappings | DONE | `273c270` + `77f935d`; `tests/test_wave_c_tool_contracts.py`; review PASS `.superpowers/sdd/task-c1-review.md` + follow-up PASS | |
| G1 | Tool contract gate | DONE | `088890b`..`77f935d`; named attacks held; Important dispatch honesty closed | |
| C2 | MCP server | DONE | commit `2c1fb75`; `tests/test_wave_c_mcp.py`; review PASS `.superpowers/sdd/task-c2-review.md` | |
| G2 | MCP gate | DONE | `77f935d`..`2c1fb75`; review PASS; no Critical/Important | |
| C3 | Intent/orchestration/clarification | IN_PROGRESS | `tests/test_wave_c_orchestration.py`; keyword `route()` onto `TOOL_CONTRACTS`; G3 not claimed | |
| G3 | Orchestration gate | NOT_STARTED | | |
| C4 | Grounded explanations/provenance | NOT_STARTED | | |
| G4 | Grounding gate | NOT_STARTED | | |
| C5 | Risk Query UI + MCP docs | NOT_STARTED | | |
| G5 | UX/devex gate | NOT_STARTED | | |
| C6 | Eval harness + adversarial cases | NOT_STARTED | | |
| G6 | Safety/eval gate | NOT_STARTED | | |
| C7 | Demo + hostile review + CI | NOT_STARTED | | |
| G7 | Wave C final gate | NOT_STARTED | | |

Overall: C0–G2 DONE; C3 IN_PROGRESS
