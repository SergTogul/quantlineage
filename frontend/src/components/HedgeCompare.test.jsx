import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { HedgeCompare } from './ScenarioBuilder.jsx'
import { API_BASE, server } from '../test/mswServer.js'
import { API_V1 } from '../api.js'

const demoPortfolio = {
  id: 'demo',
  name: 'Demo',
  positions: [{ id: 'eq-1', type: 'equity', symbol: 'SPY', quantity: 100 }],
}

describe('HedgeCompare request boundary', () => {
  it('POSTs formal Crash equity −0.20, never display −20', async () => {
    let body = null
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/stress/formal/compare`, async ({ request }) => {
        body = await request.json()
        return HttpResponse.json({
          hedge_cost: 0,
          var_improvement: 1,
          es_improvement: 1,
          base_var_99: 100,
          hedged_var_99: 90,
          base_expected_shortfall_99: 120,
          hedged_expected_shortfall_99: 110,
          methodology: 'DELTA_GAMMA',
          scenarios: [{ scenario: 'Crash', base_pnl: -10, hedged_pnl: -4, improvement: 6 }],
          factor_exposure_changes: [],
        })
      }),
    )
    const user = userEvent.setup()
    render(<HedgeCompare portfolio={demoPortfolio} />)
    await user.click(screen.getByRole('button', { name: 'Compare hedge' }))
    await waitFor(() => expect(body).not.toBeNull())

    const shocks = body.scenarios[0].shocks
    expect(shocks.every((s) => s.factor_type === 'equity' && s.amount === -0.2)).toBe(true)
    expect(shocks.some((s) => s.amount === -20)).toBe(false)
    expect(body.hedged_portfolio.positions[0].quantity).toBe(0)
  })
})
