import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { ScenarioBuilder } from './ScenarioBuilder.jsx'
import { API_BASE, server } from '../test/mswServer.js'
import { API_V1 } from '../api.js'

const demoPortfolio = {
  id: 'demo',
  name: 'Demo',
  positions: [{ id: 'eq-1', type: 'equity', symbol: 'SPY', quantity: 100 }],
}

describe('ScenarioBuilder', () => {
  it('shows empty state and validates missing scenario name locally', async () => {
    const user = userEvent.setup()
    render(<ScenarioBuilder portfolio={demoPortfolio} />)

    expect(screen.getByText(/No scenario run yet/i)).toBeInTheDocument()

    await user.clear(screen.getByLabelText(/scenario name/i))
    await user.click(screen.getByRole('button', { name: 'Run scenario' }))

    expect(await screen.findByText(/name is required/i)).toBeInTheDocument()
    expect(screen.queryByText('Equity Crash')).not.toBeInTheDocument()
  })

  it('loads evaluation result from MSW API fixture (no client risk math)', async () => {
    const user = userEvent.setup()
    render(<ScenarioBuilder portfolio={demoPortfolio} />)

    await user.click(screen.getByRole('button', { name: 'Run scenario' }))

    await waitFor(() => {
      expect(screen.getByText('Equity Crash')).toBeInTheDocument()
    })
    expect(screen.getByText(/Loss \$12\.0K/)).toBeInTheDocument()
    expect(screen.getByText(/MODERATE/)).toBeInTheDocument()
  })

  it('surfaces API errors from the evaluate endpoint', async () => {
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/stress/formal/evaluate/custom`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500, statusText: 'Internal Server Error' })),
    )
    const user = userEvent.setup()
    render(<ScenarioBuilder portfolio={demoPortfolio} />)

    await user.click(screen.getByRole('button', { name: 'Run scenario' }))

    expect(await screen.findByText(/500 Internal Server Error/)).toBeInTheDocument()
  })
})
