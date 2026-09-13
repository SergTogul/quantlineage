import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import HistoricalAnalytics from './HistoricalAnalytics.jsx'
import { API_BASE, server } from '../test/mswServer.js'
import { API_V1 } from '../api.js'

const demoPortfolio = {
  id: 'demo',
  name: 'Demo Book',
  version: 3,
  positions: [{ type: 'equity', id: 'spy', symbol: 'SPY', quantity: 100 }],
}

const UNITS = {
  returns: 'fraction',
  drawdown: 'fraction_of_peak_negative',
  volatility: 'annualized_fraction',
  var_es: 'currency_loss',
  wealth: 'end_of_period_index',
}

const BENCH_UNITS = {
  returns: 'fraction',
  excess_return: 'fraction',
  beta: 'dimensionless',
  correlation: 'dimensionless',
  tracking_error: 'annualized_fraction',
  relative_drawdown: 'fraction_of_peak_relative_wealth_negative',
  var_es: 'currency_loss',
  wealth: 'end_of_period_index',
}

function fixture(overrides = {}) {
  return {
    portfolio_id: 'demo',
    portfolio_version: 3,
    historical_dataset_id: 'demo-multi-factor-history',
    historical_dataset_version: 'abc123',
    market_snapshot_id: 'snap-demo',
    start: '2024-01-02',
    end: '2024-11-15',
    frequency: 'DAILY',
    methodology: 'DELTA_GAMMA',
    annualization: {
      periods_per_year: 252,
      return_method: 'cagr',
      volatility_method: 'sqrt_time',
      sample_ddof: 1,
    },
    risk_free_rate: 0,
    market_value: 2_630_000,
    cumulative_return: 0.0248,
    annualized_return: 0.105,
    annualized_volatility: 0.12,
    max_drawdown: -0.083,
    sharpe: 0.85,
    var_95: 31_000,
    var_99: 44_100,
    expected_shortfall_99: 51_900,
    wealth: [
      { as_of: '2024-01-02', value: 1 },
      { as_of: '2024-03-29', value: 1.0248 },
    ],
    cumulative: [
      { as_of: '2024-01-02', value: 0 },
      { as_of: '2024-03-29', value: 0.0248 },
    ],
    drawdown: [
      { as_of: '2024-01-02', value: 0 },
      { as_of: '2024-01-15', value: -0.083 },
      { as_of: '2024-03-29', value: -0.02 },
    ],
    period_returns: [],
    rolling_volatility: [
      { as_of: '2024-02-01', value: 0.11 },
      { as_of: '2024-03-29', value: 0.12 },
    ],
    best_period: { start: '2024-02-01', end: '2024-02-02', return_fraction: 0.02 },
    worst_period: { start: '2024-01-14', end: '2024-01-15', return_fraction: -0.03 },
    notes: [],
    dropped_dates: [],
    observation_count: 62,
    units: UNITS,
    benchmark: {
      instrument_id: 'equity:US:SPY',
      factor_column: 'EquitySpot:SPY',
      observation_count: 62,
      cumulative_return: 0.03,
      excess_return: -0.0052,
      correlation: 0.72,
      beta: 1.15,
      tracking_error: 0.04,
      relative_drawdown: -0.05,
      var_95: 28_000,
      var_99: 40_000,
      expected_shortfall_99: 47_000,
      wealth: [
        { as_of: '2024-01-02', value: 1 },
        { as_of: '2024-03-29', value: 1.03 },
      ],
      relative_drawdown_series: [
        { as_of: '2024-01-02', value: 0 },
        { as_of: '2024-01-15', value: -0.05 },
      ],
      aligned_start: '2024-01-02',
      aligned_end: '2024-11-15',
      units: BENCH_UNITS,
    },
    ...overrides,
  }
}

function stubAnalytics(handler) {
  const bodies = []
  server.use(
    http.post(`${API_BASE}${API_V1}/risk/historical-analytics`, async ({ request }) => {
      const body = await request.json()
      bodies.push(body)
      return handler(body)
    }),
  )
  return bodies
}

describe('HistoricalAnalytics source pin', () => {
  it('does not compute Sharpe, beta, TE, vol, or drawdown in the UI source', () => {
    const here = dirname(fileURLToPath(import.meta.url))
    const src = [
      readFileSync(join(here, 'HistoricalAnalytics.jsx'), 'utf8'),
      readFileSync(join(here, '..', 'lib', 'riskVisuals.mjs'), 'utf8'),
      readFileSync(join(here, '..', 'api.js'), 'utf8'),
    ].join('\n')
    expect(src).not.toMatch(/quantile/)
    expect(src).not.toMatch(/Math\.sqrt/)
    expect(src).not.toMatch(/\*\*\s*\(/)
    expect(src).not.toMatch(/periods_per_year\s*\*|252\s*\*/)
    expect(src).not.toMatch(/cov\s*\(|tracking_error\s*=|beta\s*=\s*/)
    expect(src).not.toMatch(/sharpe\s*=\s*\(/)
  })
})

describe('HistoricalAnalytics page', () => {
  it('POSTs range, portfolio identity, and include_benchmark true', async () => {
    const bodies = stubAnalytics(() => HttpResponse.json(fixture()))
    render(<HistoricalAnalytics portfolio={demoPortfolio} />)
    await waitFor(() => expect(bodies).toHaveLength(1))
    expect(bodies[0].include_benchmark).toBe(true)
    expect(bodies[0].start).toBe('2024-01-02')
    expect(bodies[0].end).toBe('2024-11-15')
    expect(bodies[0].portfolio.id).toBe('demo')
    expect(bodies[0].portfolio.version).toBe(3)
    expect(screen.getByTestId('ha-identity')).toHaveTextContent('demo')
    expect(screen.getByTestId('ha-identity')).toHaveTextContent('3')
    expect(screen.getByTestId('ha-identity')).toHaveTextContent('demo-multi-factor-history')
    expect(screen.getByTestId('ha-identity')).toHaveTextContent('snap-demo')
    expect(screen.getByTestId('ha-identity')).toHaveTextContent('DAILY')
    expect(screen.getByTestId('ha-identity')).toHaveTextContent('DELTA_GAMMA')
    expect(screen.getByTestId('ha-identity')).toHaveTextContent('cagr')
  })

  it('fires a new POST when start or end changes', async () => {
    const bodies = stubAnalytics((body) =>
      HttpResponse.json(fixture({ start: body.start, end: body.end })),
    )
    render(<HistoricalAnalytics portfolio={demoPortfolio} />)
    await waitFor(() => expect(bodies).toHaveLength(1))
    const first = { ...bodies[0] }
    fireEvent.change(screen.getByLabelText(/end date/i), { target: { value: '2024-06-28' } })
    await waitFor(() => expect(bodies).toHaveLength(2))
    expect(bodies[1].start).toBe(first.start)
    expect(bodies[1].end).toBe('2024-06-28')
    expect(bodies[1].include_benchmark).toBe(true)
    expect(JSON.stringify(bodies[1])).not.toBe(JSON.stringify(first))
  })

  it('renders fixture fractions with unit labels, not bare 2.48', async () => {
    stubAnalytics(() => HttpResponse.json(fixture()))
    render(<HistoricalAnalytics portfolio={demoPortfolio} />)
    const summary = await screen.findByTestId('ha-summary')
    expect(summary).toHaveTextContent('2.48%')
    expect(summary).toHaveTextContent('fraction')
    expect(summary).not.toHaveTextContent(/^2\.48$/)
    expect(summary).toHaveTextContent('62')
    expect(summary).toHaveTextContent('-8.30%')
    expect(summary).toHaveTextContent('fraction_of_peak_negative')
    expect(screen.getByTestId('ha-var-es')).toHaveTextContent('$31.0K')
    expect(screen.getByTestId('ha-var-es')).toHaveTextContent('$44.1K')
    expect(screen.getByTestId('ha-var-es')).toHaveTextContent('$51.9K')
    expect(screen.getByTestId('ha-var-es')).toHaveTextContent('currency_loss')
  })

  it('shows Sharpe as undefined when the API returns null, not zero', async () => {
    stubAnalytics(() => HttpResponse.json(fixture({ sharpe: null, notes: ['sharpe_undefined_zero_volatility'] })))
    render(<HistoricalAnalytics portfolio={demoPortfolio} />)
    const sharpe = await screen.findByTestId('ha-sharpe')
    expect(sharpe).toHaveTextContent(/undefined/i)
    expect(sharpe).not.toHaveTextContent('0.00')
    expect(sharpe.textContent).not.toMatch(/(^|[^0-9.])0([^0-9.]|$)/)
  })

  it('charts API drawdown values that are ≤ 0', async () => {
    stubAnalytics(() => HttpResponse.json(fixture()))
    render(<HistoricalAnalytics portfolio={demoPortfolio} />)
    const chart = await screen.findByTestId('ha-drawdown-chart')
    const values = [...chart.querySelectorAll('[data-value]')].map((n) => Number(n.getAttribute('data-value')))
    expect(values).toEqual([0, -0.083, -0.02])
    expect(values.every((v) => v <= 0)).toBe(true)
    expect(chart).toHaveTextContent('-0.083')
  })

  it('renders nested SPY benchmark fields and does not invent beta on 400', async () => {
    stubAnalytics(() => HttpResponse.json(fixture()))
    const { unmount } = render(<HistoricalAnalytics portfolio={demoPortfolio} />)
    const bench = await screen.findByTestId('ha-benchmark')
    expect(bench).toHaveTextContent('equity:US:SPY')
    expect(bench).toHaveTextContent('EquitySpot:SPY')
    expect(bench).toHaveTextContent('1.15')
    expect(bench).toHaveTextContent('dimensionless')
    expect(bench).toHaveTextContent('annualized_fraction')
    unmount()

    stubAnalytics(() =>
      HttpResponse.json(
        { code: 'bad_request', message: 'SPY missing from frozen panel' },
        { status: 400 },
      ),
    )
    render(<HistoricalAnalytics portfolio={demoPortfolio} />)
    const err = await screen.findByRole('alert')
    expect(err).toHaveTextContent(/SPY missing from frozen panel/i)
    expect(screen.queryByTestId('ha-benchmark')).not.toBeInTheDocument()
    expect(screen.queryByText('1.15')).not.toBeInTheDocument()
  })

  it('links to existing contributors and risk-change nav hashes', async () => {
    stubAnalytics(() => HttpResponse.json(fixture()))
    render(<HistoricalAnalytics portfolio={demoPortfolio} />)
    await screen.findByTestId('ha-links')
    expect(screen.getByRole('link', { name: /contributors/i })).toHaveAttribute('href', '#var-es')
    expect(screen.getByRole('link', { name: /risk-change/i })).toHaveAttribute('href', '#var-es')
  })
})
