import { describe, expect, it } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import MarketData from './MarketData.jsx'
import { API_BASE, server } from '../test/mswServer.js'
import { API_V1 } from '../api.js'

const AAPL = {
  instrument_id: 'equity:US:AAPL',
  display_name: 'Apple Inc.',
  provider: 'yahoo',
  source_symbol: 'AAPL',
  asset_type: 'equity',
  currency: 'USD',
  supported_for_history: true,
  supported_for_snapshot: true,
  supported_for_risk_factor: true,
  risk_factor_mapping: 'EquitySpot:AAPL',
  coverage: null,
}

const TSLA = {
  instrument_id: 'equity:US:TSLA',
  display_name: 'Tesla, Inc.',
  provider: 'yahoo',
  source_symbol: 'TSLA',
  asset_type: 'equity',
  currency: 'USD',
  supported_for_history: false,
  supported_for_snapshot: false,
  supported_for_risk_factor: false,
  risk_factor_mapping: null,
  coverage: null,
}

describe('MarketData', () => {
  it('states the Wave A public-data universe does not include FX or volatility', () => {
    render(<MarketData />)
    expect(
      screen.getByRole('note'),
    ).toHaveTextContent(
      'Public-data mode currently covers US equity spot and USD Treasury-rate factors. FX and volatility remain outside the public-data Wave A universe.',
    )
  })

  it('searches Apple via the instruments API and enables Load History only when supported', async () => {
    const user = userEvent.setup()
    const queries = []
    server.use(
      http.get(`${API_BASE}${API_V1}/instruments/search`, ({ request }) => {
        const url = new URL(request.url)
        queries.push(url.searchParams.get('q'))
        return HttpResponse.json([AAPL, TSLA])
      }),
    )

    render(<MarketData />)
    await user.type(screen.getByLabelText(/instrument search/i), 'Apple')
    await user.click(screen.getByRole('button', { name: /^search$/i }))

    await waitFor(() => expect(screen.getByText('equity:US:AAPL')).toBeInTheDocument())
    expect(queries).toEqual(['Apple'])
    expect(screen.getByText('Apple Inc.')).toBeInTheDocument()
    expect(screen.getByText('Tesla, Inc.')).toBeInTheDocument()

    const aaplRow = screen.getByText('equity:US:AAPL').closest('tr')
    const tslaRow = screen.getByText('equity:US:TSLA').closest('tr')
    expect(aaplRow).toBeTruthy()
    expect(tslaRow).toBeTruthy()
    expect(within(aaplRow).getByText('yahoo')).toBeInTheDocument()
    expect(within(aaplRow).getByText('equity')).toBeInTheDocument()
    expect(within(aaplRow).getByText('USD')).toBeInTheDocument()
    expect(within(aaplRow).getByRole('button', { name: /load history/i })).toBeEnabled()
    expect(within(tslaRow).getByRole('button', { name: /load history/i })).toBeDisabled()
  })

  it('inspects quality and renders source, coverage, stale, missing, and hash', async () => {
    const user = userEvent.setup()
    const qualityCalls = []
    server.use(
      http.get(`${API_BASE}${API_V1}/instruments/search`, () => HttpResponse.json([AAPL, TSLA])),
      http.get(`${API_BASE}${API_V1}/instruments/:instrumentId/quality`, ({ request, params }) => {
        const url = new URL(request.url)
        qualityCalls.push({
          instrumentId: params.instrumentId,
          start: url.searchParams.get('start'),
          end: url.searchParams.get('end'),
        })
        return HttpResponse.json({
          source: 'yahoo',
          source_symbol: 'AAPL',
          instrument_id: 'equity:US:AAPL',
          unit: 'price',
          frequency: 'daily',
          currency: 'USD',
          adjustment: 'adjusted',
          first_observation: '2021-01-04',
          last_observation: '2021-01-08',
          observation_count: 5,
          retrieved_at: '2026-01-15T12:00:00Z',
          missing_count: 2,
          duplicate_count: 0,
          stale: true,
          content_hash: 'deadbeefcafebabe',
          normalization_version: 'wave-a-v1',
        })
      }),
    )

    render(<MarketData />)
    await user.type(screen.getByLabelText(/instrument search/i), 'Apple')
    await user.click(screen.getByRole('button', { name: /^search$/i }))
    await waitFor(() => expect(screen.getByText('equity:US:AAPL')).toBeInTheDocument())

    await user.type(screen.getByLabelText(/start date/i), '2021-01-04')
    await user.type(screen.getByLabelText(/end date/i), '2021-01-08')

    const aaplRow = screen.getByText('equity:US:AAPL').closest('tr')
    const tslaRow = screen.getByText('equity:US:TSLA').closest('tr')
    expect(within(aaplRow).getByRole('button', { name: /inspect quality/i })).toBeEnabled()
    expect(within(tslaRow).getByRole('button', { name: /inspect quality/i })).toBeDisabled()

    await user.click(within(aaplRow).getByRole('button', { name: /inspect quality/i }))
    const panel = await screen.findByRole('region', { name: /series quality/i })
    expect(qualityCalls).toEqual([
      { instrumentId: 'equity:US:AAPL', start: '2021-01-04', end: '2021-01-08' },
    ])
    expect(within(panel).getByText('yahoo')).toBeInTheDocument()
    expect(within(panel).getByText('2021-01-04 – 2021-01-08 (5)')).toBeInTheDocument()
    expect(within(panel).getByText('2021-01-08')).toBeInTheDocument()
    expect(within(panel).getByText('stale')).toBeInTheDocument()
    expect(within(panel).getByText('2')).toBeInTheDocument()
    expect(within(panel).getByText('deadbeefcafebabe')).toBeInTheDocument()
    expect(within(panel).getByText('wave-a-v1')).toBeInTheDocument()
  })

  it('loads history from the API and renders dates and values', async () => {
    const user = userEvent.setup()
    const historyCalls = []
    server.use(
      http.get(`${API_BASE}${API_V1}/instruments/search`, () => HttpResponse.json([AAPL, TSLA])),
      http.get(`${API_BASE}${API_V1}/market/history/:instrumentId`, ({ request, params }) => {
        const url = new URL(request.url)
        historyCalls.push({
          instrumentId: params.instrumentId,
          start: url.searchParams.get('start'),
          end: url.searchParams.get('end'),
        })
        return HttpResponse.json({
          source: 'yahoo',
          source_symbol: 'AAPL',
          instrument_id: 'equity:US:AAPL',
          unit: 'price',
          content_hash: 'hist-hash',
          points: [
            { observation_date: '2021-01-04', value: 129.41 },
            { observation_date: '2021-01-05', value: 130.12 },
          ],
        })
      }),
    )

    render(<MarketData />)
    await user.type(screen.getByLabelText(/instrument search/i), 'Apple')
    await user.click(screen.getByRole('button', { name: /^search$/i }))
    await waitFor(() => expect(screen.getByText('equity:US:AAPL')).toBeInTheDocument())
    await user.type(screen.getByLabelText(/start date/i), '2021-01-04')
    await user.type(screen.getByLabelText(/end date/i), '2021-01-08')

    const aaplRow = screen.getByText('equity:US:AAPL').closest('tr')
    await user.click(within(aaplRow).getByRole('button', { name: /load history/i }))
    const table = await screen.findByRole('table', { name: /history/i })
    expect(historyCalls).toEqual([
      { instrumentId: 'equity:US:AAPL', start: '2021-01-04', end: '2021-01-08' },
    ])
    expect(within(table).getByText('2021-01-04')).toBeInTheDocument()
    expect(within(table).getByText('129.41')).toBeInTheDocument()
    expect(within(table).getByText('2021-01-05')).toBeInTheDocument()
    expect(within(table).getByText('130.12')).toBeInTheDocument()
  })

  it('freezes a dataset and builds a snapshot via Wave A actions', async () => {
    const user = userEvent.setup()
    const freezeBodies = []
    const snapshotBodies = []
    server.use(
      http.get(`${API_BASE}${API_V1}/instruments/search`, () => HttpResponse.json([AAPL, TSLA])),
      http.post(`${API_BASE}${API_V1}/data/datasets`, async ({ request }) => {
        freezeBodies.push(await request.json())
        return HttpResponse.json({
          dataset_id: 'real:public:wave-a',
          dataset_version: 'dataset-hash',
          csv_path: 'abc123.csv',
        })
      }),
      http.post(`${API_BASE}${API_V1}/market/snapshots/from-public-data`, async ({ request }) => {
        snapshotBodies.push(await request.json())
        return HttpResponse.json({
          id: 'real:public:wave-a:2024-01-08:snap-hash',
          as_of: '2024-01-08',
          content_hash: 'snap-hash',
          lineage: {},
        })
      }),
    )

    render(<MarketData />)
    await user.type(screen.getByLabelText(/start date/i), '2021-01-04')
    await user.type(screen.getByLabelText(/end date/i), '2021-01-11')
    await user.type(screen.getByLabelText(/as of/i), '2024-01-08')
    await user.click(screen.getByRole('button', { name: /freeze dataset/i }))
    expect(await screen.findByText(/real:public:wave-a/)).toBeInTheDocument()
    expect(screen.getByText(/dataset-hash/)).toBeInTheDocument()
    expect(freezeBodies).toEqual([{ start: '2021-01-04', end: '2021-01-11' }])

    await user.click(screen.getByRole('button', { name: /build snapshot/i }))
    const snapshotSection = await screen.findByRole('region', { name: /public snapshot/i })
    expect(within(snapshotSection).getByText('real:public:wave-a:2024-01-08:snap-hash')).toBeInTheDocument()
    expect(within(snapshotSection).getByText('snap-hash')).toBeInTheDocument()
    expect(snapshotBodies).toEqual([{ as_of: '2024-01-08' }])
  })

  it('shows provider-down, rate-limited, and stale error banners from API codes', async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${API_BASE}${API_V1}/instruments/search`, () => HttpResponse.json([AAPL])),
      http.get(`${API_BASE}${API_V1}/market/history/:instrumentId`, () =>
        HttpResponse.json(
          { code: 'unavailable', message: 'Provider unavailable', details: null },
          { status: 503 },
        ),
      ),
      http.post(`${API_BASE}${API_V1}/market/snapshots/from-public-data`, () =>
        HttpResponse.json(
          { code: 'stale_observation', message: 'Stale observation', details: null },
          { status: 400 },
        ),
      ),
      http.post(`${API_BASE}${API_V1}/data/datasets`, () =>
        HttpResponse.json(
          { code: 'rate_limited', message: 'Provider rate limited', details: null },
          { status: 429 },
        ),
      ),
    )

    render(<MarketData />)
    await user.type(screen.getByLabelText(/instrument search/i), 'Apple')
    await user.click(screen.getByRole('button', { name: /^search$/i }))
    await waitFor(() => expect(screen.getByText('equity:US:AAPL')).toBeInTheDocument())
    await user.type(screen.getByLabelText(/start date/i), '2021-01-04')
    await user.type(screen.getByLabelText(/end date/i), '2021-01-08')
    await user.type(screen.getByLabelText(/as of/i), '2024-01-22')

    await user.click(within(screen.getByText('equity:US:AAPL').closest('tr')).getByRole('button', { name: /load history/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/unavailable/i)
    expect(screen.getByRole('alert')).toHaveTextContent(/provider unavailable/i)

    await user.click(screen.getByRole('button', { name: /build snapshot/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/stale/i)

    await user.click(screen.getByRole('button', { name: /freeze dataset/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/rate_limited/i)
  })

  it('does not call Yahoo or FRED URLs from the browser', async () => {
    const { readFileSync } = await import('node:fs')
    const { dirname, join } = await import('node:path')
    const { fileURLToPath } = await import('node:url')
    const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'MarketData.jsx'), 'utf8')
    expect(src).not.toMatch(/finance\.yahoo|stlouisfed|FRED_API_KEY/i)
  })
})
