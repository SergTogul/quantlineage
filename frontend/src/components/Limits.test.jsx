import { describe, expect, it } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Limits } from './RiskTable.jsx'
import { API_BASE, server } from '../test/mswServer.js'
import { API_V1 } from '../api.js'

const demoPortfolio = {
  id: 'demo',
  name: 'Demo',
  positions: [{ id: 'eq-1', type: 'equity', symbol: 'SPY', quantity: 100 }],
}

const limitRows = [
  {
    metric: 'var_99',
    label: '99% VaR',
    scope: 'firm',
    value: 120_000,
    limit: 100_000,
    utilization_pct: 120,
    warning_threshold_pct: 80,
    status: 'BREACH',
    breached: true,
  },
  {
    metric: 'expected_shortfall_99',
    label: '99% ES',
    scope: 'firm',
    value: 82_000,
    limit: 100_000,
    utilization_pct: 82,
    warning_threshold_pct: 80,
    status: 'WARNING',
    breached: false,
  },
  {
    metric: 'dv01',
    label: 'DV01',
    scope: 'desk',
    value: 35_000,
    limit: 60_000,
    utilization_pct: 58,
    warning_threshold_pct: 80,
    status: 'OK',
    breached: false,
  },
]

describe('Limits', () => {
  it('renders API limit statuses and empty no-breach drill affordance', () => {
    render(<Limits items={[]} portfolio={demoPortfolio} />)

    expect(screen.getByRole('heading', { name: 'Limits' })).toBeInTheDocument()
    expect(screen.getByLabelText('Limit status summary')).toHaveTextContent('0 OK')
    expect(screen.getByLabelText('Limit status summary')).toHaveTextContent('0 WARNING')
    expect(screen.getByLabelText('Limit status summary')).toHaveTextContent('0 BREACH')
    expect(screen.getByText(/No breaches — drill any metric for contributors/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Drill down breaches/i })).toBeDisabled()
  })

  it('loads a per-metric drill-down report from MSW API fixture', async () => {
    const user = userEvent.setup()
    let requestBody
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/limits/drilldown`, async ({ request }) => {
        requestBody = await request.json()
        await new Promise((resolve) => setTimeout(resolve, 25))
        return HttpResponse.json({
          portfolio_id: 'demo',
          hierarchy_node: 'Firm',
          hierarchy_level: 'firm',
          items: [
            {
              hierarchy_node: 'Firm',
              metric: 'var_99',
              value: 120_000,
              limit: 100_000,
              utilization_pct: 120,
              status: 'BREACH',
              breached: true,
              contributors: [
                {
                  position_id: 'eq-1',
                  label: 'SPY equity',
                  contribution_pct: 72.5,
                  risk_amount: 87_000,
                },
              ],
            },
          ],
        })
      }),
    )
    render(<Limits items={limitRows} portfolio={demoPortfolio} />)

    expect(screen.getByLabelText('Limit status summary')).toHaveTextContent('1 OK')
    expect(screen.getByLabelText('Limit status summary')).toHaveTextContent('1 WARNING')
    expect(screen.getByLabelText('Limit status summary')).toHaveTextContent('1 BREACH')

    const varRow = screen.getByText('99% VaR').closest('tr')
    await user.click(within(varRow).getByRole('button', { name: 'Drill' }))

    await waitFor(() => {
      expect(within(varRow).getByRole('button', { name: 'Drill' })).toBeDisabled()
    })
    expect(await screen.findByText(/Scope firm: Firm · metric var_99/i)).toBeInTheDocument()
    expect(screen.getByText(/BREACH · 120%/)).toBeInTheDocument()
    expect(screen.getByText('SPY equity')).toBeInTheDocument()
    expect(screen.getByText('72.5%')).toBeInTheDocument()
    expect(requestBody).toMatchObject({
      portfolio: demoPortfolio,
      metric: 'var_99',
      breaches_only: false,
      top_n: 5,
    })
  })

  it('shows empty drill-down response for a metric with no contributors', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/limits/drilldown`, () =>
        HttpResponse.json({
          portfolio_id: 'demo',
          hierarchy_node: 'Firm',
          hierarchy_level: 'firm',
          items: [],
        })),
    )
    render(<Limits items={limitRows} portfolio={demoPortfolio} />)

    const dv01Row = screen.getByText('DV01').closest('tr')
    await user.click(within(dv01Row).getByRole('button', { name: 'Drill' }))

    expect(await screen.findByText(/No drill-down rows returned/i)).toBeInTheDocument()
  })

  it('surfaces API errors from limit drill-down', async () => {
    const user = userEvent.setup()
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/limits/drilldown`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500, statusText: 'Internal Server Error' })),
    )
    render(<Limits items={limitRows} portfolio={demoPortfolio} />)

    await user.click(screen.getByRole('button', { name: 'Drill down breaches' }))

    expect(await screen.findByText(/500 Internal Server Error/)).toBeInTheDocument()
  })
})
