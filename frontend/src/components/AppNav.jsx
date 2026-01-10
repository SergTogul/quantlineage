import { NAV_SECTIONS } from '../lib/nav.mjs'

export default function AppNav({ active, onSelect }) {
  return (
    <nav className="app-nav" aria-label="Main">
      <div className="app-nav-brand">
        <span className="eyebrow">RISKFORGE</span>
        <strong>Risk Terminal</strong>
      </div>
      <ul className="app-nav-list">
        {NAV_SECTIONS.map((s) => {
          const selected = s.id === active
          return (
            <li key={s.id}>
              <button
                type="button"
                className={selected ? 'app-nav-item active' : 'app-nav-item'}
                aria-current={selected ? 'page' : undefined}
                onClick={() => onSelect(s.id)}
              >
                <span className="app-nav-label">{s.label}</span>
                <span className="app-nav-hint">{s.hint}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
