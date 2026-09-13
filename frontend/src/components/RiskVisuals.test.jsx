import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { Contributors } from './RiskTable.jsx'
import { ESContributions, RatesShowcase } from './Analytics.jsx'
import { FactorExposureHeatmap, StressPnlHeatmap } from './Heatmaps.jsx'
import Overview from './Overview.jsx'
import { API_BASE, server } from '../test/mswServer.js'
import { API_V1 } from '../api.js'

const here = dirname(fileURLToPath(import.meta.url))

function readSrc(...parts) {
  return readFileSync(join(here, ...parts), 'utf8')
}

const SHOWCASE = {
  portfolio_id: 'rates-macro',
  market_snapshot_id: 'demo:rates-macro',
  conventions: {
    shock_unit: '1bp = 1e-4 decimal',
    sensitivity_unit: 'currency P&L per +1bp',
    limitations: 'Demo OIS/SOFR-style zeros; not a production multi-curve framework.',
  },
  discount_curve: {
    name: 'USD_OIS',
    currency: 'USD',
    curve_type: 'discount',
    nodes: [
      { tenor: '2Y', years: 2, zero_rate: 0.043 },
      { tenor: '5Y', years: 5, zero_rate: 0.041 },
      { tenor: '10Y', years: 10, zero_rate: 0.0415 },
    ],
  },
  parallel_dv01: -1200.5,
  key_rate_dv01: [
    { tenor: '2Y', value: -200.25, unit: 'per_bp' },
    { tenor: '5Y', value: -410.5, unit: 'per_bp' },
    { tenor: '10Y', value: -510, unit: 'per_bp' },
  ],
}

const ES_REPORT = {
  portfolio_id: 'demo',
  methodology: 'DELTA_GAMMA',
  confidence: 0.99,
  portfolio_var: 10_000,
  portfolio_es: 12_000,
  by_position: [
    { key: 'eq-1', label: 'EQ-1', component_es: 7_000, contribution_pct: 58.3 },
  ],
  by_book: [],
  by_strategy: [],
  by_desk: [],
  by_risk_factor: [
    { key: 'EquitySpot:SPY', label: 'SPY', component_es: 8_000, contribution_pct: 66.7 },
    { key: 'RateZero:USD', label: 'USD rates', component_es: 4_000, contribution_pct: 33.3 },
  ],
  reconciliation_error_position: 0,
  reconciliation_error_book: 0,
  reconciliation_error_strategy: 0,
  reconciliation_error_desk: 0,
  reconciliation_error_risk_factor: 0,
}

describe('B3 source pin: no client risk math', () => {
  it('bars, curve, and heatmap components do not contain forbidden formulas', () => {
    const src = [
      readSrc('RiskTable.jsx'),
      readSrc('Analytics.jsx'),
      readSrc('Heatmaps.jsx'),
      readSrc('..', 'lib', 'riskVisuals.mjs'),
    ].join('\n')
    expect(src).not.toMatch(/bps_to_decimal/)
    expect(src).not.toMatch(/0\.0001/)
    expect(src).not.toMatch(/1\.645|1\.96|Math\.sqrt/)
    expect(src).not.toMatch(/key_rate_dv01[\s\S]{0,120}\.reduce|key_rate_dv01\s*\+/)
    expect(src).not.toMatch(/parallel_dv01\s*\+/)
  })
})

describe('Factor contribution bars', () => {
  it('renders API risk_amount and contribution_pct as bars', () => {
    render(
      <Contributors
        items={[
          { position_id: 'eq-1', label: 'EQ-1', risk_amount: 8_500, contribution_pct: 62.5 },
          { position_id: 'eq-2', label: 'EQ-2', risk_amount: -4_000, contribution_pct: 29.4 },
        ]}
      />,
    )
    const card = screen.getByTestId('golden-demo-contributors')
    expect(card).toHaveAttribute('id', 'var-es-contributors')
    expect(within(card).getAllByText('EQ-1').length).toBeGreaterThan(0)
    expect(within(card).getAllByText('62.5%').length).toBeGreaterThan(0)
    expect(within(card).getAllByText('$8.5K').length).toBeGreaterThan(0)
    expect(within(card).getAllByText('EQ-2').length).toBeGreaterThan(0)
    expect(within(card).getAllByText('29.4%').length).toBeGreaterThan(0)
    expect(within(card).getAllByText('-$4.0K').length).toBeGreaterThan(0)
    const bars = card.querySelectorAll('[data-testid="contribution-bar"]')
    expect(bars.length).toBe(2)
    expect(bars[0].getAttribute('style')).toMatch(/width:\s*100%/)
    expect(bars[1].getAttribute('style')).toMatch(/width:\s*47/)
  })
})

describe('ES factor contribution bars', () => {
  it('charts by_risk_factor component_es from the API only', async () => {
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/es`, () => HttpResponse.json(ES_REPORT)),
    )
    const user = userEvent.setup()
    render(<ESContributions portfolio={{ id: 'demo', positions: [] }} />)
    await user.selectOptions(screen.getByLabelText('es dimension'), 'by_risk_factor')
    await user.click(screen.getByRole('button', { name: /load es/i }))
    await waitFor(() => expect(screen.getAllByText('SPY').length).toBeGreaterThan(0))
    expect(screen.getAllByText('USD rates').length).toBeGreaterThan(0)
    expect(screen.getAllByText('$8.0K').length).toBeGreaterThan(0)
    expect(screen.getAllByText('$4.0K').length).toBeGreaterThan(0)
    expect(screen.getAllByText('66.7%').length).toBeGreaterThan(0)
    expect(screen.getAllByText('33.3%').length).toBeGreaterThan(0)
    const bars = screen.getAllByTestId('contribution-bar')
    expect(bars.length).toBe(2)
    expect(bars[0].getAttribute('style')).toMatch(/width:\s*100%/)
    expect(bars[1].getAttribute('style')).toMatch(/width:\s*50%/)
  })
})

describe('KR-DV01 tenor curve', () => {
  it('charts API key_rate_dv01 by tenor and labels parallel DV01 separately', async () => {
    server.use(
      http.get(`${API_BASE}${API_V1}/market/rates-showcase`, () => HttpResponse.json(SHOWCASE)),
    )
    render(<RatesShowcase />)
    await waitFor(() => expect(screen.getByTestId('kr-dv01-tenor-curve')).toBeTruthy())
    expect(document.getElementById('risk-factors-kr-dv01')).toBeTruthy()
    const curve = screen.getByTestId('kr-dv01-tenor-curve')
    expect(curve).toHaveTextContent('2Y')
    expect(curve).toHaveTextContent('5Y')
    expect(curve).toHaveTextContent('10Y')
    expect(curve).toHaveTextContent('-$200')
    expect(curve).toHaveTextContent('-$411')
    expect(curve).toHaveTextContent('-$510')
    expect(curve).toHaveTextContent(/KR-DV01/)
    const parallel = screen.getByTestId('parallel-dv01')
    expect(parallel).toHaveTextContent(/Parallel DV01/)
    expect(parallel).toHaveTextContent('-$1.2K')
    expect(parallel).not.toHaveTextContent('-$510')
    expect(curve).not.toHaveTextContent('Parallel DV01')
  })
})

describe('Stress P&L heatmap', () => {
  it('labels scenario P&L from API pnl, not inverted loss', () => {
    render(<StressPnlHeatmap items={[{ scenario: 'Equity crash', pnl: -9_000 }]} />)
    const heading = screen.getByRole('heading', { name: /stress p&l heatmap/i })
    expect(heading).toBeTruthy()
    expect(screen.getByText('Equity crash')).toBeTruthy()
    expect(screen.getByText('-$9.0K')).toBeTruthy()
    expect(screen.queryByText('$9.0K')).toBeNull()
    expect(screen.getByText(/API pnl/i)).toBeTruthy()
  })
})

describe('Concentration heatmap', () => {
  it('shows factor exposure concentration on Risk Factors and default Overview', () => {
    const factors = [
      { factor: 'SPY', factor_type: 'equity', bucket: 'spot', exposure: 12_000 },
      { factor: 'USD', factor_type: 'fx', bucket: 'spot', exposure: -3_000 },
    ]
    const { unmount } = render(<FactorExposureHeatmap items={factors} />)
    expect(screen.getByRole('heading', { name: 'Factor exposure heatmap' })).toBeTruthy()
    expect(screen.getByText('$12.0K')).toBeTruthy()
    expect(screen.getByText('-$3.0K')).toBeTruthy()
    unmount()

    render(
      <Overview
        summary={{ market_value: 1e6, var_99: 50_000, expected_shortfall_99: 70_000 }}
        threats={{ severe_count: 0, breach_count: 0, evaluations: [] }}
        limits={[]}
        hierarchy={null}
        stress={[]}
        factors={factors}
      />,
    )
    expect(screen.getByTestId('overview-layout-status')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Factor exposure heatmap' })).toBeTruthy()
    expect(screen.getByText('$12.0K')).toBeTruthy()
  })
})
