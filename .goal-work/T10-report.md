# T10 — Show provider state in the existing UI

## Summary

Added optional assistant metadata indicators to `RiskQuery` in `frontend/src/components/ScenarioBuilder.jsx`:

- **AI-routed** — subtle `eyebrow` label when `data.assistant` is present with `provider: openai` and `fallback: false`
- **Deterministic fallback** — muted `role="note"` footnote when `data.assistant.fallback` is true
- **No metadata** — unchanged rendering (existing card, provenance, clarification, and footer behavior preserved)

Model name, prompts, and API keys are not surfaced in the UI.

## Files changed

- `frontend/src/components/ScenarioBuilder.jsx` — `RiskQueryAssistantState` helper and wiring
- `frontend/src/components/RiskQuery.test.jsx` — two new tests plus absent-metadata assertions on existing card test
- `docs/ai/TASKS.md` — T10 marked complete

## Checks

```bash
cd frontend
npm test -- --run src/components/RiskQuery.test.jsx  # 5 passed
npm run build                                         # success
```

## Out of scope (per spec)

No API key field, browser storage, model selector, prompt editor, raw model output, or `VITE_OPENAI_*` usage.
