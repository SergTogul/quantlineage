import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AppNav from './AppNav.jsx'
import { NAV_SECTIONS } from '../lib/nav.mjs'

describe('AppNav', () => {
  it('lists all terminal sections and marks the active page', () => {
    render(<AppNav active="stress" onSelect={() => {}} />)
    for (const s of NAV_SECTIONS) {
      expect(screen.getByRole('button', { name: new RegExp(s.label) })).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: /Stress/ })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: /Overview/ })).not.toHaveAttribute('aria-current')
    expect(screen.getByText('QUANTLINEAGE')).toBeInTheDocument()
  })

  it('notifies parent when a section is selected', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    render(<AppNav active="overview" onSelect={onSelect} />)
    await user.click(screen.getByRole('button', { name: (n) => n.startsWith('Limits') }))
    expect(onSelect).toHaveBeenCalledWith('limits')
  })

  it('reports a theme change from the Dark / Light switch', async () => {
    const user = userEvent.setup()
    const onThemeChange = vi.fn()
    render(<AppNav active="overview" onSelect={() => {}} theme="dark" onThemeChange={onThemeChange} />)
    await user.click(screen.getByRole('button', { name: 'Light' }))
    expect(onThemeChange).toHaveBeenCalledWith('light')
  })
})
