import { afterEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { API_V1, loadDashboard } from './api.js'
import { API_BASE, server } from './test/mswServer.js'
import { RISK_RUN_POLL_MS } from './lib/risk.mjs'

const DASHBOARD_KEYS = [
  'portfolio',
  'summary',
  'stress',
  'threats',
  'contributors',
  'limits',
  'factors',
  'varReport',
  'hierarchy',
  'attribution',
]

const DEMO_PORTFOLIO = { id: 'demo', name: 'Demo', positions: [] }

const batchFixture = Object.fromEntries(
  DASHBOARD_KEYS.map((key) => [key, key === 'portfolio' ? DEMO_PORTFOLIO : { ok: key }]),
)

const FANOUT_RISK_PATHS = [
  `${API_V1}/risk/summary`,
  `${API_V1}/risk/stress`,
  `${API_V1}/risk/var`,
  `${API_V1}/risk/hierarchy`,
  `${API_V1}/risk/contributors`,
  `${API_V1}/risk/limits`,
  `${API_V1}/risk/factors`,
  `${API_V1}/risk/attribution`,
]

function refuseBody(route = `${API_V1}/risk/dashboard`) {
  return {
    code: 'bad_request',
    message: 'Invalid request',
    details: { use: '/risk/runs', route },
  }
}

afterEach(() => {
  vi.useRealTimers()
})

describe('loadDashboard', () => {
  it('calls the dashboard batch path once and does not fan out risk POSTs', async () => {
    const posted = []
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/dashboard`, async ({ request }) => {
        posted.push(new URL(request.url).pathname)
        return HttpResponse.json(batchFixture)
      }),
      ...FANOUT_RISK_PATHS.map((path) =>
        http.post(`${API_BASE}${path}`, () => {
          posted.push(path)
          return HttpResponse.json({ unexpected: true })
        }),
      ),
    )

    const data = await loadDashboard()

    expect(posted).toEqual([`${API_V1}/risk/dashboard`])
    expect(Object.keys(data).sort()).toEqual([...DASHBOARD_KEYS].sort())
    expect(data.portfolio.id).toBe('demo')
  })

  it('falls back to portfolio + dashboard risk run when HEAVY inline is refused', async () => {
    vi.useFakeTimers()
    const calls = []
    let polls = 0

    server.use(
      http.post(`${API_BASE}${API_V1}/risk/dashboard`, () => {
        calls.push('POST /risk/dashboard')
        return HttpResponse.json(refuseBody(), { status: 400 })
      }),
      http.get(`${API_BASE}${API_V1}/portfolio`, () => {
        calls.push('GET /portfolio')
        return HttpResponse.json(DEMO_PORTFOLIO)
      }),
      http.post(`${API_BASE}${API_V1}/risk/runs`, async ({ request }) => {
        const body = await request.json()
        calls.push(`POST /risk/runs:${body.run_type}`)
        expect(body.portfolio).toEqual(DEMO_PORTFOLIO)
        expect(body.run_type).toBe('dashboard')
        return HttpResponse.json(
          { id: 'run-dash-1', status: 'QUEUED', run_type: 'dashboard', results: [] },
          { status: 202 },
        )
      }),
      http.get(`${API_BASE}${API_V1}/risk/runs/:id`, ({ params }) => {
        polls += 1
        calls.push(`GET /risk/runs/${params.id}`)
        if (polls === 1) {
          return HttpResponse.json({
            id: params.id,
            status: 'RUNNING',
            run_type: 'dashboard',
            results: [],
          })
        }
        return HttpResponse.json({
          id: params.id,
          status: 'COMPLETED',
          run_type: 'dashboard',
          error_message: null,
          results: [{ result_type: 'dashboard', payload: batchFixture }],
        })
      }),
      ...FANOUT_RISK_PATHS.map((path) =>
        http.post(`${API_BASE}${path}`, () => {
          calls.push(`FANOUT ${path}`)
          return HttpResponse.json({ unexpected: true })
        }),
      ),
    )

    const pending = loadDashboard()
    await vi.advanceTimersByTimeAsync(RISK_RUN_POLL_MS)
    const data = await pending

    expect(calls).toEqual([
      'POST /risk/dashboard',
      'GET /portfolio',
      'POST /risk/runs:dashboard',
      'GET /risk/runs/run-dash-1',
      'GET /risk/runs/run-dash-1',
    ])
    expect(calls.some((c) => c.startsWith('FANOUT'))).toBe(false)
    expect(Object.keys(data).sort()).toEqual([...DASHBOARD_KEYS].sort())
    expect(data.portfolio.id).toBe('demo')
    expect(data.stress).toEqual({ ok: 'stress' })
  })

  it('throws when refuse path ends in a FAILED risk run', async () => {
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/dashboard`, () =>
        HttpResponse.json(refuseBody(), { status: 400 }),
      ),
      http.get(`${API_BASE}${API_V1}/portfolio`, () => HttpResponse.json(DEMO_PORTFOLIO)),
      http.post(`${API_BASE}${API_V1}/risk/runs`, () =>
        HttpResponse.json(
          { id: 'run-fail-1', status: 'QUEUED', run_type: 'dashboard', results: [] },
          { status: 202 },
        ),
      ),
      http.get(`${API_BASE}${API_V1}/risk/runs/:id`, ({ params }) =>
        HttpResponse.json({
          id: params.id,
          status: 'FAILED',
          run_type: 'dashboard',
          error_message: 'worker blew up',
          results: [],
        }),
      ),
    )

    // First GET is immediate (FAILED is terminal) — no poll sleep.
    await expect(loadDashboard()).rejects.toThrow('worker blew up')
  })

  it('throws on non-refuse 400 without falling back to risk runs', async () => {
    const calls = []
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/dashboard`, () => {
        calls.push('POST /risk/dashboard')
        return HttpResponse.json(
          { code: 'bad_request', message: 'Invalid request', details: { reason: 'other' } },
          { status: 400 },
        )
      }),
      http.get(`${API_BASE}${API_V1}/portfolio`, () => {
        calls.push('GET /portfolio')
        return HttpResponse.json(DEMO_PORTFOLIO)
      }),
      http.post(`${API_BASE}${API_V1}/risk/runs`, () => {
        calls.push('POST /risk/runs')
        return HttpResponse.json({ id: 'nope' }, { status: 202 })
      }),
    )

    await expect(loadDashboard()).rejects.toThrow('400')
    expect(calls).toEqual(['POST /risk/dashboard'])
  })

  it('throws on 500 without falling back to risk runs', async () => {
    const calls = []
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/dashboard`, () => {
        calls.push('POST /risk/dashboard')
        return HttpResponse.json({ message: 'boom' }, { status: 500 })
      }),
      http.get(`${API_BASE}${API_V1}/portfolio`, () => {
        calls.push('GET /portfolio')
        return HttpResponse.json(DEMO_PORTFOLIO)
      }),
      http.post(`${API_BASE}${API_V1}/risk/runs`, () => {
        calls.push('POST /risk/runs')
        return HttpResponse.json({ id: 'nope' }, { status: 202 })
      }),
    )

    await expect(loadDashboard()).rejects.toThrow('500')
    expect(calls).toEqual(['POST /risk/dashboard'])
  })
})
