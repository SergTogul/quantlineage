export default function ThemeSwitch({ theme, onChange }) {
  return (
    <div className="theme-switch" role="group" aria-label="Theme">
      <button
        type="button"
        className={theme === 'dark' ? 'theme-switch-btn active' : 'theme-switch-btn'}
        aria-pressed={theme === 'dark'}
        onClick={() => onChange?.('dark')}
      >
        Dark
      </button>
      <button
        type="button"
        className={theme === 'light' ? 'theme-switch-btn active' : 'theme-switch-btn'}
        aria-pressed={theme === 'light'}
        onClick={() => onChange?.('light')}
      >
        Light
      </button>
    </div>
  )
}
