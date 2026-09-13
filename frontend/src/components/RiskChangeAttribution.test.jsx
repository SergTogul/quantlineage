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
    changed_fields: ['portfolio_version', 'historical_dataset_version', 'calculation_config'],
    t0: {
      run_id: 'run-t0',
      portfolio_id: 'demo',
      portfolio_version: 1,
      market_snapshot_id: 'snap-t0',
      historical_dataset_id: 'real:public:wave-a',
      historical_dataset_version: 'v1',
      methodology: 'DELTA_GAMMA',
      calculation_config: { lookback_days: 252 },
    },
    t1: {
      run_id: 'run-t1',
      portfolio_id: 'demo',
      portfolio_version: 2,
      market_snapshot_id: 'snap-t0',
      historical_dataset_id: 'real:public:wave-a',
      historical_dataset_version: 'v2',
      methodology: 'DELTA_GAMMA',
      calculation_config: { lookback_days: 504 },
    },
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

function stubCompare(report = FLAGSHIP_REPORT) {
  let compareBody = null
  let created = 0
  const postedRuns = []
  server.use(
    http.post(`${API_BASE}${API_V1}/risk/runs`, async ({ request }) => {
      created += 1
      const body = await request.json()
      postedRuns.push(body)
      const id = created === 1 ? 'run-t0' : 'run-t1'
      return HttpResponse.json({
        id,
        portfolio_id: body.portfolio?.id ?? 'demo',
        market_snapshot_id: created === 1 ? 'snap-t0' : body.market_snapshot_id,
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
      return HttpResponse.json(report)
    }),
  )
  return { getCompareBody: () => compareBody, postedRuns }
}

async function compareFlagship(report) {
  const ctx = stubCompare(report)
  const user = userEvent.setup()
  render(<RiskChangeAttribution portfolio={demoPortfolio} />)
  await user.click(screen.getByRole('button', { name: /compare t0\/t1/i }))
  await waitFor(() => expect(ctx.getCompareBody()).not.toBeNull())
  return { user, ...ctx }
}

describe('RiskChangeAttribution flagship card', () => {
  it('does not reconstruct residual or compute VaR in the source', () => {
    const here = dirname(fileURLToPath(import.meta.url))
    const src = [
      readFileSync(join(here, 'Analytics.jsx'), 'utf8'),
      readFileSync(join(here, '..', 'lib', 'riskVisuals.mjs'), 'utf8'),
    ].join('\n')
    expect(src).not.toMatch(/quantile|Math\.sqrt|historicalVaR|var_99\s*\*/)
    expect(src).not.toMatch(/total_change\s*-/)
    expect(src).not.toMatch(/previous_risk\s*\+/)
    expect(src).toMatch(/compareRiskRuns|riskChangeReportSummary/)
  })

  it('displays backend compare fields and does not compute VaR locally', async () => {
    const { postedRuns, getCompareBody } = await compareFlagship()
    expect(postedRuns).toHaveLength(2)
    expect(postedRuns[0].portfolio.id).toBe('demo')
    expect(postedRuns[1].portfolio.id).not.toBe('demo')
    expect(postedRuns[1].portfolio.id).toBe('demo-t1-spy-x1.5')
    expect(postedRuns[1].portfolio.positions[0].quantity).toBe(150)
    expect(postedRuns[1].market_snapshot_id).toBe('snap-t0')
    expect(getCompareBody().t0_run_id).toBeTruthy()
    expect(getCompareBody().t1_run_id).toBeTruthy()
    expect(screen.getByText(/Why did my risk change/i)).toBeTruthy()
    expect(screen.getByText(/currency loss/i)).toBeTruthy()
    expect(screen.getAllByText(/residual \/ interactions/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/EquitySpot:SPY/)).toBeTruthy()
    expect(screen.getByRole('link', { name: /run-t0/i })).toBeTruthy()
    expect(screen.getByRole('link', { name: /run-t1/i })).toBeTruthy()
  })

  it('charts waterfall steps from API fields without client residual math', async () => {
    await compareFlagship()
    const chart = screen.getByTestId('risk-change-waterfall')
    const steps = [...chart.querySelectorAll('[data-step]')]
    expect(steps).toHaveLength(5)
    expect(steps[0]).toHaveAttribute('data-step', 't0')
    expect(steps[0]).toHaveTextContent('$1.0K')
    expect(steps[1]).toHaveAttribute('data-step', 'portfolio')
    expect(steps[1]).toHaveTextContent('$300')
    expect(steps[2]).toHaveAttribute('data-step', 'market')
    expect(steps[2]).toHaveTextContent('$110')
    expect(steps[3]).toHaveAttribute('data-step', 'residual')
    expect(steps[3]).toHaveTextContent('residual / interactions')
    expect(steps[3]).toHaveTextContent('$10')
    expect(steps[4]).toHaveAttribute('data-step', 't1')
    expect(steps[4]).toHaveTextContent('$1.4K')
  })

  it('keeps the residual label visible when residual is 0', async () => {
    await compareFlagship({ ...FLAGSHIP_REPORT, residual: 0, explained_change: 410 })
    const residual = screen.getByTestId('waterfall-step-residual')
    expect(residual).toHaveTextContent('residual / interactions')
    expect(residual).toHaveTextContent('$0')
    expect(screen.getAllByText(/residual \/ interactions/i).length).toBeGreaterThan(0)
  })

  it('renders identity fields from the compare fixture', async () => {
    await compareFlagship()
    const identity = screen.getByTestId('risk-change-identity')
    expect(identity).toHaveTextContent('1')
    expect(identity).toHaveTextContent('2')
    expect(identity).toHaveTextContent('snap-t0')
    expect(identity).toHaveTextContent('real:public:wave-a')
    expect(identity).toHaveTextContent('v1')
    expect(identity).toHaveTextContent('v2')
    expect(identity).toHaveTextContent('DELTA_GAMMA')
    expect(identity).toHaveTextContent('lookback_days')
  })

  it('drills Firm → Desk → Book → Trade and lists factors from factor_contributors', async () => {
    const { user } = await compareFlagship()
    const drill = screen.getByTestId('risk-change-drill')
    expect(drill).toHaveTextContent(/firm/i)
    expect(drill).toHaveTextContent('RiskForge')
    await user.click(screen.getByRole('button', { name: /desk Global Macro/i }))
    expect(drill).toHaveTextContent(/desk/i)
    expect(drill).toHaveTextContent('Global Macro')
    await user.click(screen.getByRole('button', { name: /book Equity/i }))
    expect(drill).toHaveTextContent(/book/i)
    expect(drill).toHaveTextContent('Equity')
    await user.click(screen.getByRole('button', { name: /trade eq-1/i }))
    expect(drill).toHaveTextContent(/trade/i)
    expect(drill).toHaveTextContent('eq-1')
    expect(screen.queryByRole('button', { name: /EquitySpot/i })).toBeNull()
    const factors = screen.getByTestId('risk-change-factors')
    expect(factors).toHaveTextContent('EquitySpot:SPY')
    expect(factors).toHaveTextContent('$110')
  })
})
