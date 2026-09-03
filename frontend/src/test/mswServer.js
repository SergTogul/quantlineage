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
  http.post(`${API_BASE}${API_V1}/risk/stress/reverse/multi`, async () =>
    HttpResponse.json({
      target_loss_pct: 0.05,
      target_loss: 3100,
      achieved_loss_pct: 0.05,
      pnl: -3100,
      base_market_value: 62000,
      converged: true,
      objective_l2: 0.12,
      shocks: [
        {
          factor: 'equity',
          required_shock: -0.14,
          shock_unit: 'relative',
          weight: 0.7,
          max_shock: 0.8,
        },
        {
          factor: 'vol',
          required_shock: 0.25,
          shock_unit: 'relative',
          weight: 0.3,
          max_shock: 0.8,
        },
      ],
      factors: ['equity', 'vol'],
      method: 'ray_search_coordinate_descent',
      iterations: 8,
      message: null,
      assumptions: [
        'Weights normalize shock search direction across selected factors.',
      ],
    })),
]

export const server = setupServer(...handlers)
