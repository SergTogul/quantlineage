import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import App from './App.jsx'
import { API_V1 } from './api.js'
import { API_BASE, server } from './test/mswServer.js'

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    loadDashboard: vi.fn(),
  }
})

import { loadDashboard } from './api'

const DASHBOARD = {
  portfolio: {
    id: 'global-macro',
    name: 'Global Macro Demo',
    version: 1,
    positions: [{ id: 'eq-1', type: 'equity', symbol: 'SPY', book: 'Equity' }],
  },
  summary: { market_value: 1_000_000, var_99: 50_000, expected_shortfall_99: 70_000 },
  stress: [],
  threats: { severe_count: 0, breach_count: 0, evaluations: [] },
  contributors: [
    { position_id: 'eq-1', label: 'EQ-1', risk_amount: 8_500, contribution_pct: 62.5 },
  ],
  limits: [],
  factors: [],
  varReport: { methods: [], contributions: [] },
  hierarchy: null,
  attribution: null,
}

afterEach(() => {
  window.location.hash = ''
})

describe('App market-data gate', () => {
  it('renders Market Data when dashboard load failed', async () => {
    window.location.hash = '#market-data'
    loadDashboard.mockRejectedValue(new Error('dashboard down'))
    render(<App />)
    expect(await screen.findByLabelText(/instrument search/i)).toBeInTheDocument()
    expect(screen.queryByText(/API error/i)).not.toBeInTheDocument()
  })

  it('renders Market Data while dashboard load is pending', async () => {
    window.location.hash = '#market-data'
    loadDashboard.mockReturnValue(new Promise(() => {}))
    render(<App />)
    await waitFor(() => expect(screen.getByLabelText(/instrument search/i)).toBeInTheDocument())
    expect(screen.queryByText(/Loading portfolio risk/i)).not.toBeInTheDocument()
  })
})

describe('App demo panel hashes', () => {
  const scrolledIds = []
  const originalScrollIntoView = HTMLElement.prototype.scrollIntoView

  beforeEach(() => {
    loadDashboard.mockReset()
    loadDashboard.mockResolvedValue(DASHBOARD)
    scrolledIds.length = 0
    HTMLElement.prototype.scrollIntoView = function scrollIntoViewSpy() {
      scrolledIds.push(this.id)
    }
  })

  afterEach(() => {
    HTMLElement.prototype.scrollIntoView = originalScrollIntoView
  })

  it('scrolls to contributors for #var-es/contributors, not the waterfall card', async () => {
    window.location.hash = '#var-es/contributors'
    render(<App />)
    const contributors = await screen.findByTestId('golden-demo-contributors')
    const waterfall = screen.getByTestId('golden-demo-risk-change')
    expect(contributors).toHaveAttribute('id', 'var-es-contributors')
    expect(waterfall).toHaveAttribute('id', 'var-es-risk-change')
    await waitFor(() => expect(scrolledIds).toContain('var-es-contributors'))
    expect(scrolledIds).not.toContain('var-es-risk-change')
  })

  it('scrolls to the risk-change waterfall card for #var-es/risk-change', async () => {
    window.location.hash = '#var-es/risk-change'
    render(<App />)
    const waterfall = await screen.findByTestId('golden-demo-risk-change')
    expect(waterfall).toHaveAttribute('id', 'var-es-risk-change')
    await waitFor(() => expect(scrolledIds).toContain('var-es-risk-change'))
    expect(scrolledIds).not.toContain('var-es-contributors')
  })

  it('scrolls to KR-DV01 for #risk-factors/kr-dv01', async () => {
    server.use(
      http.get(`${API_BASE}${API_V1}/market/rates-showcase`, () => HttpResponse.json({
        portfolio_id: 'global-macro',
        market_snapshot_id: 'demo:global-macro',
        conventions: {
          shock_unit: '1bp = 1e-4 decimal',
          sensitivity_unit: 'currency P&L per +1bp',
          limitations: 'Demo OIS/SOFR-style zeros; not a production multi-curve framework.',
        },
        discount_curve: {
          name: 'USD_OIS',
          currency: 'USD',
          curve_type: 'discount',
          nodes: [{ tenor: '2Y', years: 2, zero_rate: 0.043 }],
        },
        parallel_dv01: -1200.5,
        key_rate_dv01: [{ tenor: '2Y', value: -200.25, unit: 'per_bp' }],
      })),
    )
    window.location.hash = '#risk-factors/kr-dv01'
    render(<App />)
    const card = await waitFor(() => {
      const el = document.getElementById('risk-factors-kr-dv01')
      expect(el).toBeTruthy()
      return el
    })
    expect(card).toHaveTextContent(/KR-DV01/)
    await waitFor(() => expect(card).toHaveTextContent(/Parallel DV01 \(not KR-DV01\)/))
    await waitFor(() => expect(scrolledIds).toContain('risk-factors-kr-dv01'))
  })
})
