# Block help (“?”) — design

**Date:** 2026-09-04  
**Owner:** Frontend / Risk UX  
**Status:** Approved for planning (pending final user review of this spec)

## Goal

Add a small `?` helper next to every titled analysis card (e.g. Stress P&L heatmap, Hedge Compare). Clicking it opens a short popup with a 1–2 sentence explanation of what the block shows and how it is calculated.

## Decisions (locked)

| Topic | Choice |
|---|---|
| Scope | Every titled analysis card (`h3` cards), not overview KPI tiles, Terminal map, or nav section `h2`s |
| Interaction | Click `?` to toggle; click outside or Esc to dismiss; only one popover open at a time |
| Copy tone | Technical: what the block shows + how RiskForge calculates it |
| Structure | Separate component file + separate copy file (no inline help strings in cards) |

## Architecture

### New files (required separation)

1. **`frontend/src/components/BlockHelp.jsx`**  
   Reusable control: `?` button + popover. Looks up copy by `id` from the lib map. Owns open/close, outside-click, Esc, and single-open behavior.

2. **`frontend/src/lib/blockHelp.mjs`**  
   Sole source of help text: `id → { body }` (optional short `title` if needed). No UI logic here.

3. **Tests**  
   - `frontend/src/lib/blockHelp.test.js` — every wired id has non-empty body; bodies are 1–2 sentences / reasonable length.  
   - `frontend/src/components/BlockHelp.test.jsx` — toggle open/close, Esc, outside click, missing id graceful fallback.

### Wiring

Each analysis card title becomes a compact title row: `<h3>…</h3>` + `<BlockHelp id="…" />`.

Cards that already use `.card-title-row` keep badges/legends on the right; help sits next to the `h3` on the left.

Existing muted subtitles under titles remain; help is additive.

### Out of scope

- Overview `MetricCard` KPIs  
- Overview Terminal map collage tiles  
- Nav section headers (`SectionFrame` `h2`)  
- Backend/API changes  
- Inventing or displaying new risk numbers in help copy

## UX & accessibility

- Small circular `?` control beside the card title (does not replace the title).
- `aria-label="About this block"`; `aria-expanded` reflects open state.
- Popover ~260–300px wide; body text from `blockHelp.mjs` only.
- Opens on click; closes on toggle, outside click, or Esc.
- Opening another block’s help closes the previous (single open).
- Help copy describes methodology only — no fabricated portfolio numbers.

## Styling

Minimal CSS in `frontend/src/styles.css` (or colocated if the project later splits component CSS):

- `.block-help` wrapper (inline with title)
- `.block-help-btn` (small muted circle)
- `.block-help-popover` (absolute panel, elevated above card content)

Match existing dark terminal palette (`#8ea0b5` muted text, `#233040` borders) — no new design system.

## Copy catalog (`blockHelp.mjs`)

Source of truth: `frontend/src/lib/blockHelp.mjs` (technical what/how bodies). Summary:

| id | Card title | Calculation focus |
|---|---|---|
| `positions` | Positions | Portfolio inventory only — no pricing/risk |
| `portfolio-hierarchy` | Portfolio Hierarchy | HierarchyEngine node aggregates under MarketSnapshot |
| `hierarchy-risk-heatmap` | Hierarchy risk heatmap | Display scale on HierarchyEngine NAV/VaR/ES |
| `risk-factors` | Risk Factors | RiskFactorEngine: Σ Δ / vega / DV01 / FX Δ by factor |
| `factor-exposure-heatmap` | Factor exposure heatmap | Same exposures as factor × bucket matrix |
| `var-es` | VaR / Expected Shortfall | Historical vs parametric 99% VaR & ES |
| `component-var` | Component VaR Contributors | Parametric component VaR shares from API |
| `es-contributions` | ES Contributions | ES decomposed by hierarchy/factor dimension |
| `var-compare` | VaR Methodology Compare | LINEAR / Δ-Γ / full-reval on same factor panel |
| `risk-change-attribution` | Risk Change Attribution | Δ(VaR/ES) waterfall; residual = total − explained |
| `stress-pnl-heatmap` | Stress P&L heatmap | Full-reval PnL = shocked MV − base MV |
| `stress-tests` | Stress Tests | StressEngine shock + full revaluation |
| `threat-scenarios` | Threat Scenario Evaluation | Loss% NAV vs threshold; threat bands / breach |
| `reverse-stress` | Reverse Stress | Binary search one-factor shock to target loss% |
| `reverse-stress-multi` | Multi-Factor Reverse Stress | Ray search + coordinate descent multi-factor |
| `scenario-builder` | Scenario Builder | Custom FactorShocks → full reval → loss metrics |
| `hedge-compare` | Hedge Compare | Base vs hedged VaR/ES, stress PnL, factor Δ |
| `risk-query` | Risk Query | Deterministic tool routing from NL question |
| `pnl-explain` | P&L Explain | Sensitivity/Taylor driver decomposition + residual |
| `limit-utilization-heatmap` | Limit utilization heatmap | utilization = \|value\|/limit; OK/warn/breach bands |
| `limits` | Limits | LimitEngine status + drill-down contributors |
| `risk-runs` | Risk Runs | Async RiskRun enqueue/poll lifecycle |

## Files touched (implementation)

- **Add:** `BlockHelp.jsx`, `blockHelp.mjs`, tests as above  
- **Edit titles:** `App.jsx` (Positions), `Heatmaps.jsx`, `RiskTable.jsx`, `ScenarioBuilder.jsx`, `Analytics.jsx`  
- **Styles:** `frontend/src/styles.css`

## Testing

- Unit: every catalog id has a non-empty `body`; no empty strings.
- Component: open/close via button; Esc closes; outside click closes; unknown id does not crash (muted “No help available” or similar).
- Smoke: existing frontend Vitest suite still passes (`npm test` / project script for frontend).

## Non-goals / constraints

- Do not duplicate pricing/risk formulas in the UI beyond descriptive copy.
- Do not change API contracts or backend calculation code.
- Keep commits/task batch narrow: help UX only.

## Implementation follow-up

After this spec is approved, create an implementation plan (`docs/superpowers/plans/…`) via the writing-plans workflow, then implement.
