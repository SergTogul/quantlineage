import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { RatesShowcase, RunProvenance } from './Analytics.jsx'
import { API_BASE, server } from '../test/mswServer.js'
import { API_V1 } from '../api.js'

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

const PROVENANCE = {
  risk_run_id: 'run-9',
  portfolio_id: 'rates-macro',
  portfolio_version: 1,
  market_snapshot_id: 'demo:rates-macro',
  as_of: 'current',
  historical_dataset_id: 'demo-multi-factor-history',
  historical_dataset_version: 'v1',
  pricing_engine_version: 'builtin-0.3.0',
  methodology: 'DELTA_GAMMA',
  scenario_set: ['rates-steepener'],
  calculation_config: { observations: 50, seed: 7 },
  duration_seconds: 1.5,
  status: 'COMPLETED',
  release_sha: 'abc123',
}

describe('RatesShowcase panel', () => {
  it('renders curve nodes and KR-DV01 from the API payload only', async () => {
    const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'Analytics.jsx'), 'utf8')
    expect(src).not.toMatch(/bps_to_decimal|0\.0001\s*\*|key_rate_dv01\s*\+/)
    server.use(
      http.get(`${API_BASE}${API_V1}/market/rates-showcase`, () => HttpResponse.json(SHOWCASE)),
    )
    render(<RatesShowcase />)
    await waitFor(() => expect(screen.getByText('USD_OIS')).toBeTruthy())
    expect(screen.getByText('2Y')).toBeTruthy()
    expect(screen.getByText('10Y')).toBeTruthy()
    expect(screen.getByText(/per \+1bp/i)).toBeTruthy()
    expect(screen.getByText(/not a production multi-curve/i)).toBeTruthy()
  })
})

describe('RunProvenance panel', () => {
  it('displays GET provenance fields and does not invent a release SHA', async () => {
    const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'Analytics.jsx'), 'utf8')
    expect(src).not.toMatch(/git describe|Math\.random/)
    server.use(
      http.get(`${API_BASE}${API_V1}/risk/runs/:id/provenance`, () => HttpResponse.json(PROVENANCE)),
    )
    render(<RunProvenance runId="run-9" />)
    await waitFor(() => expect(screen.getByText('run-9')).toBeTruthy())
    expect(screen.getByText('demo-multi-factor-history')).toBeTruthy()
    expect(screen.getByText('v1')).toBeTruthy()
    expect(screen.getByText('builtin-0.3.0')).toBeTruthy()
    expect(screen.getByText('DELTA_GAMMA')).toBeTruthy()
    expect(screen.getByText('abc123')).toBeTruthy()
  })
})
