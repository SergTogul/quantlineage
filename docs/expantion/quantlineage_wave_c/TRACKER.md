# Wave C Tracker

| ID | Task | Status | Evidence | Blocker |
|---|---|---|---|---|
| C0 | Inventory deterministic services | DONE | `C0_INTEGRATION_MAP.md`; RF-019 `query.py` + Wave A catalog/history/quality + Wave B compare/KR-DV01/historical-analytics mapped; no MCP | |
| C1 | Tool schemas/service mappings | IN_PROGRESS | `backend/app/risk/tool_contracts.py` + `query.py` allowlist; `tests/test_wave_c_tool_contracts.py`; G1 not claimed | |
| G1 | Tool contract gate | NOT_STARTED | | |
| C2 | MCP server | NOT_STARTED | | |
| G2 | MCP gate | NOT_STARTED | | |
| C3 | Intent/orchestration/clarification | NOT_STARTED | | |
| G3 | Orchestration gate | NOT_STARTED | | |
| C4 | Grounded explanations/provenance | NOT_STARTED | | |
| G4 | Grounding gate | NOT_STARTED | | |
| C5 | Risk Query UI + MCP docs | NOT_STARTED | | |
| G5 | UX/devex gate | NOT_STARTED | | |
| C6 | Eval harness + adversarial cases | NOT_STARTED | | |
| G6 | Safety/eval gate | NOT_STARTED | | |
| C7 | Demo + hostile review + CI | NOT_STARTED | | |
| G7 | Wave C final gate | NOT_STARTED | | |

Overall: C0 DONE; C1 IN_PROGRESS; G1–G7 NOT_STARTED
