# T12 — Fixed evaluation suite

## Status

Complete.

## Changes

- Added `backend/tests/test_ai_evals.py` with 45 table-driven cases across six categories: supported paraphrases (16), missing identifiers (7), unsupported advice (6), prompt injection (6), invalid arguments (5), and secret extraction (2).
- Tests exercise deterministic routing (`RiskQueryEngine.route` / `answer`), application validation (`validate_tool_call`), and model-path seams (`answer_with_model` with scripted models). No network calls.

## Acceptance

| Criterion | Result |
|-----------|--------|
| ≥16 supported paraphrases | 16 cases; routing 16/16 (≥15/16 threshold) |
| ≥6 missing-identifier | 7 cases; all clarify with zero tool execution |
| ≥6 unsupported advice/forecast | 6 cases; all refuse with zero execution |
| ≥6 prompt-injection | 6 cases; deterministic + model path block execution |
| ≥4 invalid-argument | 5 cases; validation blocks + model path executes zero tools |
| ≥2 secret-extraction | 2 cases; refusal with no leaked secret markers |
| Executed tools allowlisted+valid | Parametrized execution check validates routed args |
| Deterministic, network-free | `socket.socket` blocked in network-free test |

## Checks

```bash
cd backend
python3 -m pytest tests/test_ai_evals.py -q
```

Result: 74 passed.

## Concerns

- Supported paraphrase execution uses an extended fixture stub; tools requiring RiskRun IDs are covered in missing-identifier cases instead of full execution paths.
- Forecast-like phrasing that still matches VaR keywords (e.g. "what will VaR be tomorrow") is intentionally out of scope for the advisory bucket; deterministic router behavior is unchanged.
