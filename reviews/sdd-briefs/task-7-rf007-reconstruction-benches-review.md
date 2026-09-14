# Task 7 Review — RF-007 reconstruction benches

**Base:** `749e1e4`  
**Head:** `78c1d0e`  
**Reviewer:** independent task review (spec + quality)

### Spec Compliance

- ✅ Spec compliant

Requirements in the diff: European option reconstruction (not `quantity * spot`) at the same N×S with live spot/vol/rate/div; per-engine checksums; skip-or-run QuantLib; P&L gap at `rel=2e-3`; isolated RSS via a subprocess per impl; N=100×50 behind `QUANTLINEAGE_NIGHTLY=1` with sibling job `full-reval-n100`; R0.6.1 / R0.6.7 cash-equity pins unchanged; RF-007 still IN PROGRESS / KEEP OPEN; no SLA floors; not in PR-FULL `needs:`.

### Issues

#### Critical
None.

#### Important
None.

#### Minor (carry-forward)
- `_reconstruction_row` clones `_engine_row` (drift risk).
- `rss_isolated: True` hardcoded on the child row.
- Nightly job `QUANTLINEAGE_PRICING_ENGINE: builtin` is misleading (engines constructed directly).
- `--reconstruction-only` unused by the nightly job.

### Assessment

**Task quality:** Approved

**Reasoning:** Reconstruction-honest option full-reval, isolated RSS, and nightly N=100 without touching cash-equity identity, methodology, or RF-007 close state.
