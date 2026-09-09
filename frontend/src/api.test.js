import { afterEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import {
  API_V1,
  evaluateCustomScenario,
  explainPnL,
  loadDashboard,
  reverseStress,
} from './api.js'
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

function mockRiskRunPoll({ runType, payload, runId = 'run-1' }) {
  let polls = 0
  return [
    http.post(`${API_BASE}${API_V1}/risk/runs`, async ({ request }) => {
      const body = await request.json()
      expect(body.run_type).toBe(runType)
      return HttpResponse.json(
        { id: runId, status: 'QUEUED', run_type: runType, results: [] },
        { status: 202 },
      )
    }),
    http.get(`${API_BASE}${API_V1}/risk/runs/:id`, ({ params }) => {
      polls += 1
      if (polls === 1) {
        return HttpResponse.json({
          id: params.id,
          status: 'RUNNING',
          run_type: runType,
          results: [],
        })
      }
      return HttpResponse.json({
        id: params.id,
        status: 'COMPLETED',
        run_type: runType,
        error_message: null,
        results: [{ result_type: runType, payload }],
      })
    }),
  ]
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

describe('HEAVY UI RiskRun fallback', () => {
  const scenario = {
    id: 'eq-crash',
    name: 'Equity crash',
    category: 'factor',
    shocks: [{ factor_type: 'equity', key: 'SPY', amount: -0.1, bucket: 'SPY' }],
  }

  it('evaluateCustomScenario falls back to stress_evaluate RiskRun on refuse', async () => {
    const asyncPayload = { evaluations: [{ scenario_id: 'async-ok', pnl: -12 }] }
    let syncHits = 0
    let runBody = null

    server.use(
      http.post(`${API_BASE}${API_V1}/risk/stress/formal/evaluate/custom`, () => {
        syncHits += 1
        return HttpResponse.json(
          refuseBody(`${API_V1}/risk/stress/formal/evaluate/custom`),
          { status: 400 },
        )
      }),
      http.post(`${API_BASE}${API_V1}/risk/runs`, async ({ request }) => {
        runBody = await request.json()
        expect(runBody.run_type).toBe('stress_evaluate')
        expect(runBody.portfolio).toEqual(DEMO_PORTFOLIO)
        expect(runBody.request.scenarios).toEqual([scenario])
        return HttpResponse.json(
          { id: 'run-eval-1', status: 'QUEUED', run_type: 'stress_evaluate', results: [] },
          { status: 202 },
        )
      }),
      http.get(`${API_BASE}${API_V1}/risk/runs/:id`, ({ params }) =>
        HttpResponse.json({
          id: params.id,
          status: 'COMPLETED',
          run_type: 'stress_evaluate',
          error_message: null,
          results: [{ result_type: 'stress_evaluate', payload: asyncPayload }],
        }),
      ),
    )

    const data = await evaluateCustomScenario(DEMO_PORTFOLIO, scenario)

    expect(syncHits).toBe(1)
    expect(runBody.run_type).toBe('stress_evaluate')
    expect(data).toEqual(asyncPayload)
  })

  it('evaluateCustomScenario keeps sync POST when gate is off', async () => {
    const syncPayload = { evaluations: [{ scenario_id: 'gate-off' }] }
    let runHits = 0
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/stress/formal/evaluate/custom`, () =>
        HttpResponse.json(syncPayload),
      ),
      http.post(`${API_BASE}${API_V1}/risk/runs`, () => {
        runHits += 1
        return HttpResponse.json({ id: 'nope' }, { status: 202 })
      }),
    )

    const data = await evaluateCustomScenario(DEMO_PORTFOLIO, scenario)
    expect(data).toEqual(syncPayload)
    expect(runHits).toBe(0)
  })

  it('explainPnL falls back to attribution RiskRun on refuse', async () => {
    vi.useFakeTimers()
    const attrRequest = {
      previous_portfolio: DEMO_PORTFOLIO,
      current_portfolio: { ...DEMO_PORTFOLIO, id: 'demo-scaled' },
      dt_years: 0,
    }
    const asyncPayload = { items: [{ label: 'position', pnl: 1.5 }], total_pnl: 1.5 }

    server.use(
      http.post(`${API_BASE}${API_V1}/risk/attribution`, () =>
        HttpResponse.json(refuseBody(`${API_V1}/risk/attribution`), { status: 400 }),
      ),
      ...mockRiskRunPoll({
        runType: 'attribution',
        payload: asyncPayload,
        runId: 'run-attr-1',
      }),
    )

    const pending = explainPnL(attrRequest)
    await vi.advanceTimersByTimeAsync(RISK_RUN_POLL_MS)
    const data = await pending
    expect(data).toEqual(asyncPayload)
  })

  it('reverseStress falls back to reverse_stress RiskRun on refuse', async () => {
    vi.useFakeTimers()
    const asyncPayload = {
      factor: 'equity',
      required_shock: -0.22,
      target_loss_pct: 0.1,
      converged: true,
    }

    server.use(
      http.post(`${API_BASE}${API_V1}/risk/stress/reverse`, () =>
        HttpResponse.json(refuseBody(`${API_V1}/risk/stress/reverse`), { status: 400 }),
      ),
      ...mockRiskRunPoll({
        runType: 'reverse_stress',
        payload: asyncPayload,
        runId: 'run-rev-1',
      }),
    )

    const pending = reverseStress(DEMO_PORTFOLIO, 'equity', 0.1)
    await vi.advanceTimersByTimeAsync(RISK_RUN_POLL_MS)
    const data = await pending
    expect(data).toEqual(asyncPayload)
  })
})
