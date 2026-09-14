import { NAV_SECTIONS } from '../lib/nav.mjs'
import ThemeSwitch from './ThemeSwitch.jsx'

export default function AppNav({ active, onSelect, theme = 'dark', onThemeChange }) {
  return (
    <nav className="app-nav" aria-label="Main">
      <div className="app-nav-brand">
        <strong>QUANTLINEAGE</strong>
        <span>Risk & Attribution</span>
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
      <ThemeSwitch theme={theme} onChange={onThemeChange} />
    </nav>
  )
}
