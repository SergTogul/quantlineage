# Stage 10.4 Golden Demo Notes

Presenter script: [`../demo_script.md`](../demo_script.md).

This folder’s screenshots (`quantlineage_demo_01_overview.png` …) were captured against the local deterministic API. They are **demo** illustrations, not observed-market evidence. Prefer live UI numbers over screenshot figures.

## Seed

Compose lifespan seeds demo books. Optional idempotent re-seed:

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/seed_golden_demo.py
```

Re-running does not duplicate catalog rows. Historical input remains packaged synthetic replay (`demo-multi-factor-history`), not live data.

## E2E

`e2e/tests/golden-demo.spec.ts` walks the same critical path (catalog → VaR/ES/Greeks → hierarchy → stress → Compare T0/T1 → hedge → GET-run provenance → in-app limitations).
