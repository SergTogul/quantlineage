# T02 Report — Add SDK, dotenv, and env templates

## Status

**DONE**

## Summary

Added pinned `openai` and `python-dotenv` dependencies to `backend/requirements.txt`, created root `.env.example`, and extended `.env.shared.example` with AI provider settings. No dotenv lifecycle wiring (T07) and no `config.py` changes.

## Files changed

| File | Change |
|------|--------|
| `backend/requirements.txt` | `openai>=1.59,<4`, `python-dotenv>=1.0,<2` |
| `.env.example` | New local template with blank `OPENAI_API_KEY` and AI settings |
| `.env.shared.example` | Same AI settings for shared/production profile |

## Acceptance mapping

| Criterion | Result |
|-----------|--------|
| `.env.example` contains blank `OPENAI_API_KEY` | `OPENAI_API_KEY=` (empty value) |
| Example files contain provider/model/timeout/round settings | All four `QUANTLINEAGE_*` vars present in both files |
| `.env` and `.env.shared` are ignored | `git check-ignore` confirms both |
| No live-looking secret in git diff | Blank key only; no `sk-` values |
| `pip install -r requirements.txt` resolves | Installed on Python 3.12.3 |
| `test_ai_config.py` still passes | 14 passed |

## Checks

```bash
git check-ignore .env .env.shared
# .env
# .env.shared

cd backend
python3 -m pip install -r requirements.txt
python3 -m pytest tests/test_ai_config.py -q
# 14 passed in 0.39s
```

## Commits

| SHA | Subject |
|-----|---------|
| `5b002f2` | Add SDK, dotenv, and env templates (T02) |

## Out of scope (T03+)

- Strict OpenAI tool schemas
- dotenv load at application startup (T07)
- Compose env wiring (T13)

## Concerns

None.
