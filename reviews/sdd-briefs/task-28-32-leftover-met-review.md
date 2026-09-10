# Independent review — leftover-wave MET closes (QA-024 / RF-017 / RF-018 / RF-019)

**Range:** `90e40a2` → `b592be9`
**Verdict:** **APPROVE CLOSE** all four. These are not ACCEPTED / DEFERRED dressed as done.

| Finding | Score | Evidence |
|---|---|---|
| QA-024 | **MET** | `tests/test_qa024_ql_demo_range.py` vs `data/demo_risk_artifact.json`; nightly `quantlib-e2e` |
| RF-017 | **MET** | ABI version / errors / length / `pnl_from_arrays` / serial-below-4096 in `test_native_kernel.py` + `kernel_test.cpp`. Product Historical VaR stays Python/NumPy **by design**. |
| RF-018 | **MET** | Display −20% / 100bp → −0.20 / 0.01; OpenAPI snapshot + drift pin; `npm ci` / no `"latest"`. Not a TypeScript rewrite. |
| RF-019 | **MET** | Pydantic JSON Schema per `RiskToolName`; allowlist = `TOOL_CONTRACTS`; injection/ambiguity/advisory evals; no live LLM. |

Tests run by reviewer: backend 56 passed; frontend RF-018 36 passed.
