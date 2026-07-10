import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { RiskChangeAttribution } from './Analytics.jsx'
import { API_BASE, server } from '../test/mswServer.js'
import { API_V1 } from '../api.js'

const demoPortfolio = {
  id: 'demo',
  name: 'Demo',
  firm: 'RiskForge',
  desk: 'Global Macro',
  positions: [{ id: 'eq-1', type: 'equity', symbol: 'SPY', quantity: 100, book: 'Equity' }],
}

const FLAGSHIP_REPORT = {
  t0_run_id: 'run-t0',
  t1_run_id: 'run-t1',
  metric: 'var_99',
  unit: 'currency loss',
  sign_convention: 'positive total_change means the selected metric increased',
  previous_risk: 1000,
  current_risk: 1420,
  total_change: 420,
  portfolio_trade_change: 300,
  market_change: 110,
  explained_change: 410,
  residual: 10,
  residual_name: 'residual / interactions',
  disclosed_changes: ['calculation_config'],
  identity: {
    changed_fields: ['calculation_config'],
    t0: { run_id: 'run-t0', portfolio_id: 'demo', portfolio_version: 1 },
    t1: { run_id: 'run-t1', portfolio_id: 'demo', portfolio_version: 1 },
  },
  factor_contributors: [
    {
      factor_id: 'EquitySpot:SPY',
      factor_type: 'equity',
      factor: 'SPY',
      bucket: 'SPY',
      delta_risk: 110,
    },
  ],
  hierarchy_contributors: [
    {
      level: 'firm',
      name: 'RiskForge',
      path: 'RiskForge',
      delta_risk: 300,
      children: [
        {
          level: 'desk',
          name: 'Global Macro',
          path: 'RiskForge/Global Macro',
          delta_risk: 300,
          children: [
            {
              level: 'book',
              name: 'Equity',
              path: 'RiskForge/Global Macro/Equity',
              delta_risk: 300,
              children: [
                {
                  level: 'trade',
                  name: 'eq-1',
                  path: 'RiskForge/Global Macro/Equity/eq-1',
                  position_id: 'eq-1',
                  delta_risk: 300,
                  children: [],
                },
              ],
            },
          ],
        },
      ],
    },
  ],
  items: [{ driver: 'Position changes', delta_risk: 300 }],
}

describe('RiskChangeAttribution flagship card', () => {
  it('displays backend compare fields and does not compute VaR locally', async () => {
    const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'Analytics.jsx'), 'utf8')
    expect(src).not.toMatch(/quantile|Math\.sqrt|historicalVaR|var_99\s*\*/)
    expect(src).toMatch(/compareRiskRuns|riskChangeReportSummary/)

    let compareBody = null
    let created = 0
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/runs`, async () => {
        created += 1
        const id = created === 1 ? 'run-t0' : 'run-t1'
        return HttpResponse.json({
          id,
          portfolio_id: 'demo',
          status: 'COMPLETED',
          run_type: 'summary',
          results: [{ result_type: 'summary', payload: { var_99: 1000 } }],
        }, { status: 202 })
      }),
      http.get(`${API_BASE}${API_V1}/risk/runs/:id`, ({ params }) =>
        HttpResponse.json({
          id: params.id,
          portfolio_id: 'demo',
          status: 'COMPLETED',
          run_type: 'summary',
          results: [],
        })),
      http.post(`${API_BASE}${API_V1}/risk/runs/compare`, async ({ request }) => {
        compareBody = await request.json()
        return HttpResponse.json(FLAGSHIP_REPORT)
      }),
    )

    const user = userEvent.setup()
    render(<RiskChangeAttribution portfolio={demoPortfolio} />)
    await user.click(screen.getByRole('button', { name: /compare t0\/t1/i }))
    await waitFor(() => expect(compareBody).not.toBeNull())
    expect(compareBody.t0_run_id).toBeTruthy()
    expect(compareBody.t1_run_id).toBeTruthy()
    expect(screen.getByText(/currency loss/i)).toBeTruthy()
    expect(screen.getByText(/residual \/ interactions/i)).toBeTruthy()
    expect(screen.getByText(/EquitySpot:SPY/)).toBeTruthy()
    expect(screen.getByRole('link', { name: /run-t0/i })).toBeTruthy()
    expect(screen.getByRole('link', { name: /run-t1/i })).toBeTruthy()
  })
})
