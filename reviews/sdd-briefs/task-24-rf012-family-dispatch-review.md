# Task 24 Review — RF-012 family-keyed dispatch (after instance-handler fix)

**Base:** `205c3db`  
**Head:** `3857892`

### Spec Compliance

- ✅ Spec compliant after `getattr(self, handler_name)` fix

### Strengths

Family-keyed `value()`; one overlay module; instance-resolved handlers so QuantLib eval-date spies fire.

### Issues

#### Critical / Important
None after the fix.

#### Minor
AST pins do not assert name/`getattr` storage; Builtin overlay double-read; `attribution.py` Position-isinstance out of slice.

### Assessment

**Task quality:** Approved

**Lead disposition:** RF-012 **CLOSED**. Named residual: discriminated Position/Terms unions in `domain/`.
