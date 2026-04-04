import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { API_V1, loadDashboard } from './api.js'
import { API_BASE, server } from './test/mswServer.js'

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

const batchFixture = Object.fromEntries(
  DASHBOARD_KEYS.map((key) => [key, key === 'portfolio' ? { id: 'demo', name: 'Demo', positions: [] } : { ok: key }]),
)

describe('loadDashboard', () => {
  it('calls the dashboard batch path once and does not fan out risk POSTs', async () => {
    const posted = []
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/dashboard`, async ({ request }) => {
        posted.push(new URL(request.url).pathname)
        return HttpResponse.json(batchFixture)
      }),
    )

    const data = await loadDashboard()

    expect(posted).toEqual([`${API_V1}/risk/dashboard`])
    expect(Object.keys(data).sort()).toEqual([...DASHBOARD_KEYS].sort())
    expect(data.portfolio.id).toBe('demo')
  })
})
