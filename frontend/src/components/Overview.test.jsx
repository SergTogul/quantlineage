import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Overview from './Overview.jsx'

const summary = { market_value: 1e6, var_99: 50_000, expected_shortfall_99: 70_000 }
const threats = {
  severe_count: 1,
  breach_count: 2,
  evaluations: [{ scenario: 'Crash', loss: 12_000 }],
}
const limits = [
  { metric: 'var_99', label: '99% VaR', status: 'BREACH', breached: true, utilization_pct: 110 },
]
const props = {
  summary,
  threats,
  limits,
  hierarchy: null,
  stress: [],
  factors: [],
}

describe('Overview', () => {
  it('leads with book status from API payloads and keeps the KPI strip', () => {
    render(<Overview {...props} />)
    const status = screen.getByTestId('book-status')
    expect(status).toHaveTextContent('Breach')
    expect(status).toHaveTextContent(/1 limit breach/)
    expect(screen.getByTestId('golden-demo-metrics')).toHaveTextContent('Market Value')
    expect(screen.getByTestId('golden-demo-metrics')).toHaveTextContent('99% VaR')
    expect(screen.getByTestId('golden-demo-metrics')).toHaveTextContent('99% Expected Shortfall')
    expect(screen.getByRole('heading', { name: 'Terminal map' })).toBeInTheDocument()
    expect(screen.getByTestId('overview-layout-status')).toBeInTheDocument()
    expect(screen.queryByRole('tablist', { name: 'Overview composition' })).not.toBeInTheDocument()
    const where = screen.getByRole('region', { name: 'Exceptions' })
    const metrics = screen.getByTestId('golden-demo-metrics')
    expect(status.compareDocumentPosition(where) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(where.compareDocumentPosition(metrics) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('drills from status and exception rows without inventing numbers', async () => {
    const user = userEvent.setup()
    const onNavigate = vi.fn()
    render(<Overview {...props} onNavigate={onNavigate} />)
    await user.click(screen.getByRole('button', { name: 'Open limit breaches' }))
    expect(onNavigate).toHaveBeenCalledWith('limits')
    await user.click(screen.getByRole('button', { name: '99% VaR 110% util' }))
    expect(onNavigate).toHaveBeenCalledWith('limits')
  })

  it('two-pane desk docks the selected exception', async () => {
    const user = userEvent.setup()
    render(<Overview {...props} layout="desk" />)
    expect(screen.getByTestId('overview-layout-desk')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '99% VaR 110% util' }))
    expect(screen.getByTestId('overview-dock')).toHaveTextContent('99% VaR')
    expect(screen.getByTestId('overview-dock')).toHaveTextContent('110%')
  })

  it('exception queue is the blotter, not a jump map', () => {
    render(<Overview {...props} layout="queue" />)
    expect(screen.getByTestId('overview-layout-queue')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Exception queue' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Terminal map' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '99% VaR 110% util' })).toBeInTheDocument()
  })

  it('mosaic shows four live monitors from API payloads', () => {
    render(<Overview {...props} layout="mosaic" />)
    const mosaic = screen.getByTestId('overview-layout-mosaic')
    expect(mosaic).toHaveTextContent('VaR tape')
    expect(mosaic).toHaveTextContent('Limits')
    expect(mosaic).toHaveTextContent('Threats')
    expect(mosaic).toHaveTextContent('Hierarchy')
  })

  it('command GO puts the query control first', () => {
    render(<Overview {...props} layout="command" portfolio={{ id: 'p', positions: [] }} />)
    expect(screen.getByTestId('overview-layout-command')).toBeInTheDocument()
    expect(screen.getByTestId('golden-demo-risk-query')).toBeInTheDocument()
  })

  it('hierarchy book uses the tree as the overview', () => {
    render(<Overview {...props} layout="hierarchy" />)
    expect(screen.getByTestId('overview-layout-hierarchy')).toBeInTheDocument()
    expect(screen.getByTestId('golden-demo-hierarchy')).toBeInTheDocument()
  })

  it('overnight tape leads with the loaded dashboard print', () => {
    render(<Overview {...props} layout="tape" />)
    expect(screen.getByTestId('overview-layout-tape')).toHaveTextContent('Loaded dashboard')
    expect(screen.getByTestId('overview-layout-tape')).toHaveTextContent('99% VaR')
  })

  it('function-key strip exposes specialist teasers', async () => {
    const user = userEvent.setup()
    const onNavigate = vi.fn()
    render(<Overview {...props} layout="keys" onNavigate={onNavigate} />)
    expect(screen.getByTestId('overview-layout-keys')).toHaveTextContent('F3')
    await user.click(screen.getByRole('button', { name: /F4 VaR & ES/ }))
    await user.click(screen.getByRole('button', { name: 'Open VaR & ES' }))
    expect(onNavigate).toHaveBeenCalledWith('var-es')
  })
})
