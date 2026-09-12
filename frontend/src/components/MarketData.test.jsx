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

    await user.click(within(aaplRow).getByRole('button', { name: /load history/i }))
    expect(screen.getByText(/history load is not available yet/i)).toBeInTheDocument()
  })

  it('does not call Yahoo or FRED URLs from the browser', async () => {
    const { readFileSync } = await import('node:fs')
    const { dirname, join } = await import('node:path')
    const { fileURLToPath } = await import('node:url')
    const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'MarketData.jsx'), 'utf8')
    expect(src).not.toMatch(/finance\.yahoo|stlouisfed|FRED_API_KEY/i)
  })
})
