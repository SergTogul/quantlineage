import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { ReverseStressMulti } from './ScenarioBuilder.jsx'
import { API_BASE, server } from '../test/mswServer.js'
import { API_V1 } from '../api.js'

const demoPortfolio = {
  id: 'demo',
  name: 'Demo',
  positions: [{ id: 'eq-1', type: 'equity', symbol: 'SPY', quantity: 100 }],
}

describe('ReverseStressMulti', () => {
  it('shows empty state and validates fewer than two factors', async () => {
    const user = userEvent.setup()
    render(<ReverseStressMulti portfolio={demoPortfolio} />)

    expect(screen.getByText(/No multi-factor reverse run yet/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Multi-Factor Reverse Stress' })).toBeInTheDocument()

    await user.click(screen.getByLabelText('factor vol'))
    await user.click(screen.getByRole('button', { name: 'Solve multi-factor' }))

    expect(await screen.findByText(/at least two factors/i)).toBeInTheDocument()
    expect(screen.queryByText('Converged')).not.toBeInTheDocument()
  })

  it('loads multi-factor result from MSW fixture (no client risk math)', async () => {
    const user = userEvent.setup()
    render(<ReverseStressMulti portfolio={demoPortfolio} />)

    await user.click(screen.getByRole('button', { name: 'Solve multi-factor' }))

    await waitFor(() => {
      expect(screen.getByText('Converged')).toBeInTheDocument()
    })
    const result = screen.getByText('Converged').closest('.reverse-multi-result')
    expect(result).toBeTruthy()
    expect(result.querySelector('tbody')).toHaveTextContent('equity')
    expect(result.querySelector('tbody')).toHaveTextContent('vol')
    expect(screen.getByText(/ray_search_coordinate_descent/)).toBeInTheDocument()
    expect(screen.getByText(/Required shock/i)).toBeInTheDocument()
  })

  it('surfaces API errors from reverse/multi', async () => {
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/stress/reverse/multi`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500, statusText: 'Internal Server Error' })),
    )
    const user = userEvent.setup()
    render(<ReverseStressMulti portfolio={demoPortfolio} />)

    await user.click(screen.getByRole('button', { name: 'Solve multi-factor' }))

    expect(await screen.findByText(/500 Internal Server Error/)).toBeInTheDocument()
  })
})
