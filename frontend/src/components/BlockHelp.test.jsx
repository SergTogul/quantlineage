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
    expect(screen.getByRole('dialog')).toHaveTextContent(/base vs hedged|VaR\/ES/i)
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
