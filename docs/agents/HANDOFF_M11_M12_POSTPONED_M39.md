# Handoff — M11/M12 POSTPONED + M3.9 methodology

## Task
Postpone M11/M12 on ROADMAP; publish M3.9 multi-factor reverse-stress methodology docs.

## Owner
Lead Architect (coordination); Stress/docs residual for M3.9

## Summary
- No M11/M12 code was committed or left uncommitted (working tree was clean; prior M11 attempt never landed).
- ROADMAP Progress table + M11/M12 sections marked **POSTPONED** (product decision; not COMPLETE; task lists retained).
- M3.9 closed with honest methodology doc + fixture tests (not a certified global optimum).

## Files changed
- `ROADMAP.md`
- `docs/methodology/multi_factor_reverse_stress.md` (new)
- `backend/tests/test_m39_methodology_docs.py` (new)
- `README.md` (link)
- `docs/agents/HANDOFF_M11_M12_POSTPONED_M39.md` (this file)

## Public/interface changes
- None (docs + ROADMAP only; PricingEngine untouched)

## Numerical conventions
- N/A (documentation of existing M3.6 solver assumptions)

## Tests added/updated
- `test_m39_methodology_doc_exists_and_denies_global_optimum`
- `test_m39_methodology_doc_covers_engine_assumptions`

## Commands executed
```bash
cd backend && PYTHONPATH=. .venv/bin/python -m pytest tests/test_m39_methodology_docs.py -q --tb=short
```

## Results
- Backend: 2 passed (focused M3.9 suite)
- No M11/M12 implementation
- Push: `1283105` on `origin/master` (https://github.com/SergTogul/riskforge-mvp)

## Known limitations / risks
- M6 remains PARTIAL (no VaR wall-time SLA)
- M12.4 / M12.6 still open when M12 is unblocked (broader methodology pack)
- M11/M12 must not be started until Lead/user unblocks

## Follow-up / next owner
- Owner: Lead Architect / C++ Performance (product)
- Requested action: Prefer next residual **M6 SLA disposition** (document accepted PARTIAL or define real wall-time SLA — do not invent COMPLETE)
- Blocking?: no for other residuals; **yes** for any M11/M12 work until unblock
