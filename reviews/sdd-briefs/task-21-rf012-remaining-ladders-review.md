# Task 21 Review — RF-012 remaining capability ladders

**Base:** `bd60ff8`  
**Head:** `9615d57`

### Spec Compliance

- ✅ Spec compliant

`calculate_typed` includes cap/floor/swaption. `required_factors_for_position` uses `named_risk_factors`. Cache schema ids live on the capability registry. KEEP OPEN is honest.

### Strengths

Shared `named_risk_factors` for panel identity and typed exposures. FINDINGS names remaining ladders and does not CLOSE.

### Issues

#### Critical / Important
None.

#### Minor
1. `named_risk_factors` can drop declared kinds without failing (equity/FX `RateZero` skipped).
2. Exhaustiveness test only asserts a non-empty result.
3. `_EQUITY_FAMILY_TYPES` remains a family set in `cache.py`.
4. Handoff cites `02_QUANT_PRICING_ENGINEER.md`; charter is `03_`.

### Assessment

**Task quality:** Approved

**Lead disposition:** RF-012 **KEEP OPEN**. Builtin/QuantLib `value()` isinstance, duplicated overlay, domain unions, and `position_label` remain parallel edits.
