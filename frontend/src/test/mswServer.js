/**
 * MSW node server for component/API client tests (M9.1).
 * Fixtures are display-only; numbers are not computed by the UI under test.
 */
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { API_V1 } from '../api.js'

/** Matches frontend/src/api.js default BASE when VITE_API_BASE_URL is unset. */
export const API_BASE = 'http://localhost:8000'

export const handlers = [
  http.post(`${API_BASE}${API_V1}/risk/stress/evaluate/custom`, async () =>
    HttpResponse.json({
      evaluations: [
        {
          scenario: 'Equity Crash',
          loss: 12_000,
          loss_pct_nav: 0.05,
          threat_level: 'MODERATE',
          breached: false,
        },
      ],
    })),
]

export const server = setupServer(...handlers)
