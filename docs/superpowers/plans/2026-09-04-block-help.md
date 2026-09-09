# Block Help (“?”) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `?` helper next to every titled analysis card that opens a short popover explaining what the block shows and how it is calculated.

**Architecture:** Separate copy map (`frontend/src/lib/blockHelp.mjs`) and reusable control (`frontend/src/components/BlockHelp.jsx`). Cards only pass `id`; help text never lives inline in card components. Click toggles; outside click and Esc dismiss; only one popover open via a `block-help-open` window event.

**Tech Stack:** React 19, Vitest, Testing Library, existing `styles.css` terminal palette.

## Global Constraints

- Help copy and UI live in **separate files** (`blockHelp.mjs` + `BlockHelp.jsx`); cards only reference `id`.
- Scope: every titled analysis card (`h3`); not overview KPI tiles, Terminal map, or nav `h2`s.
- Copy tone: plain lead-in + brief method note; no invented risk numbers.
- UI must not compute risk; display/help only.
- Do not commit unless the user explicitly asks (workspace commit rule).
- Spec: `docs/superpowers/specs/2026-09-04-block-help-design.md`

## File structure

| File | Responsibility |
|---|---|
| `frontend/src/lib/blockHelp.mjs` | `BLOCK_HELP` map + `getBlockHelp(id)` |
| `frontend/src/lib/blockHelp.test.js` | Catalog completeness / body quality |
| `frontend/src/components/BlockHelp.jsx` | `?` button + popover behavior |
| `frontend/src/components/BlockHelp.test.jsx` | Open/close, Esc, outside, missing id |
| `frontend/src/styles.css` | `.block-title`, `.block-help*` |
| `App.jsx`, `Heatmaps.jsx`, `RiskTable.jsx`, `ScenarioBuilder.jsx`, `Analytics.jsx` | Wire `<BlockHelp id="…" />` beside each `h3` |

---

### Task 1: Help copy catalog (`blockHelp.mjs`)

**Files:**
- Create: `frontend/src/lib/blockHelp.mjs`
- Test: `frontend/src/lib/blockHelp.test.js`

**Interfaces:**
- Produces: `getBlockHelp(id: string) => { body: string } | null`
- Produces: `BLOCK_HELP` frozen map with all catalog ids from the spec
- Produces: `BLOCK_HELP_IDS` array of all ids (for tests / wiring checks)

- [ ] **Step 1: Write the failing test**

```js
import { test } from 'vitest'
import assert from 'node:assert/strict'
import { BLOCK_HELP, BLOCK_HELP_IDS, getBlockHelp } from './blockHelp.mjs'

const EXPECTED_IDS = [
  'positions', 'portfolio-hierarchy', 'hierarchy-risk-heatmap', 'risk-factors',
  'factor-exposure-heatmap', 'var-es', 'component-var', 'es-contributions',
  'var-compare', 'risk-change-attribution', 'stress-pnl-heatmap', 'stress-tests',
  'threat-scenarios', 'reverse-stress', 'reverse-stress-multi', 'scenario-builder',
  'hedge-compare', 'risk-query', 'pnl-explain', 'limit-utilization-heatmap',
  'limits', 'risk-runs',
]

test('catalog covers every expected block id with non-empty body', () => {
  assert.deepEqual([...BLOCK_HELP_IDS].sort(), [...EXPECTED_IDS].sort())
  for (const id of EXPECTED_IDS) {
    const entry = getBlockHelp(id)
    assert.ok(entry, `missing ${id}`)
    assert.equal(typeof entry.body, 'string')
    assert.ok(entry.body.trim().length >= 40, `${id} body too short`)
    assert.ok(entry.body.trim().length <= 320, `${id} body too long`)
  }
})

test('getBlockHelp returns null for unknown id', () => {
  assert.equal(getBlockHelp('no-such-block'), null)
})

test('BLOCK_HELP is frozen', () => {
  assert.ok(Object.isFrozen(BLOCK_HELP))
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/lib/blockHelp.test.js`  
Expected: FAIL (module not found)

- [ ] **Step 3: Write catalog implementation**

Implement `frontend/src/lib/blockHelp.mjs` with exact bodies from the design spec table (all 22 ids). Export:

```js
export const BLOCK_HELP = Object.freeze({ /* id: Object.freeze({ body: '...' }) */ })
export const BLOCK_HELP_IDS = Object.freeze(Object.keys(BLOCK_HELP))
export function getBlockHelp(id) {
  return BLOCK_HELP[id] ?? null
}
```

Use the exact copy from `docs/superpowers/specs/2026-09-04-block-help-design.md` § Copy catalog.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- src/lib/blockHelp.test.js`  
Expected: PASS

---

### Task 2: `BlockHelp` component + styles

**Files:**
- Create: `frontend/src/components/BlockHelp.jsx`
- Create: `frontend/src/components/BlockHelp.test.jsx`
- Modify: `frontend/src/styles.css` (append block-help rules)

**Interfaces:**
- Consumes: `getBlockHelp(id)` from `../lib/blockHelp.mjs`
- Produces: `export default function BlockHelp({ id })`
- Behavior: click toggle; Esc / outside mousedown close; `window` event `block-help-open` with `{ detail: { id } }` for single-open; unknown id shows “No help available for this block.”

- [ ] **Step 1: Write the failing component test**

```jsx
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import BlockHelp from './BlockHelp.jsx'

describe('BlockHelp', () => {
  it('toggles popover with catalog body', async () => {
    const user = userEvent.setup()
    render(<BlockHelp id="hedge-compare" />)
    const btn = screen.getByRole('button', { name: 'About this block' })
    expect(btn).toHaveAttribute('aria-expanded', 'false')
    await user.click(btn)
    expect(btn).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('dialog')).toHaveTextContent(/SPY-flat hedge/i)
    await user.click(btn)
    expect(btn).toHaveAttribute('aria-expanded', 'false')
  })

  it('closes on Escape', async () => {
    const user = userEvent.setup()
    render(<BlockHelp id="stress-pnl-heatmap" />)
    await user.click(screen.getByRole('button', { name: 'About this block' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('closes on outside click', async () => {
    const user = userEvent.setup()
    render(
      <div>
        <BlockHelp id="limits" />
        <button type="button">outside</button>
      </div>,
    )
    await user.click(screen.getByRole('button', { name: 'About this block' }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'outside' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows fallback for unknown id', async () => {
    const user = userEvent.setup()
    render(<BlockHelp id="missing-id" />)
    await user.click(screen.getByRole('button', { name: 'About this block' }))
    expect(screen.getByRole('dialog')).toHaveTextContent(/No help available/i)
  })

  it('only one popover open at a time', async () => {
    const user = userEvent.setup()
    render(
      <div>
        <BlockHelp id="hedge-compare" />
        <BlockHelp id="limits" />
      </div>,
    )
    const buttons = screen.getAllByRole('button', { name: 'About this block' })
    await user.click(buttons[0])
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    await user.click(buttons[1])
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    expect(screen.getByRole('dialog')).toHaveTextContent(/limit/i)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/components/BlockHelp.test.jsx`  
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `BlockHelp.jsx` and CSS**

```jsx
import { useEffect, useRef, useState } from 'react'
import { getBlockHelp } from '../lib/blockHelp.mjs'

const OPEN_EVENT = 'block-help-open'

export default function BlockHelp({ id }) {
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)
  const entry = getBlockHelp(id)
  const body = entry?.body ?? 'No help available for this block.'

  useEffect(() => {
    if (!open) return undefined
    const onDoc = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false)
    }
    const onOther = (e) => {
      if (e.detail?.id !== id) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    window.addEventListener(OPEN_EVENT, onOther)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
      window.removeEventListener(OPEN_EVENT, onOther)
    }
  }, [open, id])

  function toggle() {
    const next = !open
    if (next) {
      window.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: { id } }))
    }
    setOpen(next)
  }

  return (
    <span className="block-help" ref={rootRef}>
      <button
        type="button"
        className="block-help-btn"
        aria-label="About this block"
        aria-expanded={open}
        aria-controls={open ? `block-help-${id}` : undefined}
        onClick={toggle}
      >
        ?
      </button>
      {open && (
        <div
          id={`block-help-${id}`}
          className="block-help-popover"
          role="dialog"
          aria-label="Block help"
        >
          <p>{body}</p>
        </div>
      )}
    </span>
  )
}
```

Append to `styles.css`:

```css
.block-title{display:flex;align-items:center;gap:8px;margin:0 0 16px;flex-wrap:wrap}
.block-title h3{margin:0}
.block-help{position:relative;display:inline-flex;flex-shrink:0;vertical-align:middle}
.block-help-btn{width:22px;height:22px;padding:0;border-radius:999px;border:1px solid #33445a;background:#0b1119;color:#8ea0b5;font-size:12px;font-weight:700;line-height:1;cursor:pointer}
.block-help-btn:hover,.block-help-btn[aria-expanded=true]{color:#e7edf5;border-color:#4a6a88}
.block-help-popover{position:absolute;z-index:20;top:calc(100% + 8px);left:0;width:min(300px,70vw);padding:12px 14px;background:#0e141c;border:1px solid #33445a;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.45)}
.block-help-popover p{margin:0;font-size:12px;line-height:1.45;color:#b6c4d5;font-weight:500}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- src/components/BlockHelp.test.jsx src/lib/blockHelp.test.js`  
Expected: PASS

---

### Task 3: Wire `BlockHelp` into every analysis card

**Files:**
- Modify: `frontend/src/App.jsx` (Positions)
- Modify: `frontend/src/components/Heatmaps.jsx` (4 heatmaps)
- Modify: `frontend/src/components/RiskTable.jsx` (Contributors, Limits, Stress, ThreatScenarios)
- Modify: `frontend/src/components/ScenarioBuilder.jsx` (ScenarioBuilder, ReverseStress, ReverseStressMulti, RiskQuery, HedgeCompare)
- Modify: `frontend/src/components/Analytics.jsx` (RiskFactors, VaRAnalytics, Hierarchy, Attribution, RiskRuns, RiskChangeAttribution, ESContributions, VaRCompare)

**Interfaces:**
- Consumes: `BlockHelp` default export; catalog ids from Task 1

**Pattern for plain cards:**

```jsx
import BlockHelp from './BlockHelp'

// ...
<div className="block-title">
  <h3>Hedge Compare</h3>
  <BlockHelp id="hedge-compare" />
</div>
```

**Pattern inside existing `card-title-row`:**

```jsx
<div className="card-title-row">
  <div>
    <div className="block-title">
      <h3>Stress P&amp;L heatmap</h3>
      <BlockHelp id="stress-pnl-heatmap" />
    </div>
    <div className="muted">…</div>
  </div>
  {/* legend / badges unchanged */}
</div>
```

Wire every id from Task 1’s `EXPECTED_IDS` list. For Analytics one-liners (`RiskFactors`, `VaRAnalytics`), expand enough to insert the title row without changing data logic.

- [ ] **Step 1: Apply wiring to all five files**

- [ ] **Step 2: Run full frontend suite**

Run: `cd frontend && npm test`  
Expected: all PASS

- [ ] **Step 3: Lint**

Run: `cd frontend && npm run lint`  
Expected: exit 0

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|---|---|
| Separate `BlockHelp.jsx` + `blockHelp.mjs` | 1–2 |
| Click / outside / Esc / single-open | 2 |
| All titled analysis cards | 3 |
| Copy catalog (22 ids) | 1 |
| Exclude KPI / Terminal map / nav h2 | 3 (not wired) |
| Tests | 1–2 |
| Styles match terminal | 2 |

No placeholders. Commit steps omitted per workspace commit rule.
