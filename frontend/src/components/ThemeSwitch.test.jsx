import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ThemeSwitch from './ThemeSwitch.jsx'

describe('ThemeSwitch', () => {
  it('marks the active theme and reports the other one', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<ThemeSwitch theme="dark" onChange={onChange} />)
    const dark = screen.getByRole('button', { name: 'Dark' })
    const light = screen.getByRole('button', { name: 'Light' })
    expect(dark).toHaveAttribute('aria-pressed', 'true')
    expect(light).toHaveAttribute('aria-pressed', 'false')
    await user.click(light)
    expect(onChange).toHaveBeenCalledWith('light')
  })
})
