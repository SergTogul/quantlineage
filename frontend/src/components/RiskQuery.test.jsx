import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { RiskQuery } from './ScenarioBuilder.jsx'
import { API_BASE, server } from '../test/mswServer.js'
import { API_V1 } from '../api.js'

const demoPortfolio = {
  id: 'demo',
  name: 'Demo',
  positions: [{ id: 'eq-1', type: 'equity', symbol: 'SPY', quantity: 100 }],
}

const EXAMPLES = [
  'Why did VaR change?',
  'Top contributors?',
  'Show USD 10Y KR-DV01.',
  'Run equity-down stress.',
  'Compare these RiskRuns.',
]

function queryHandler(impl) {
  server.use(
    http.post(`${API_BASE}${API_V1}/risk/query`, async ({ request }) => {
      const body = await request.json()
      return HttpResponse.json(impl(body))
    }),
  )
}

describe('RiskQuery', () => {
  it('example chips fill and submit the listed prompts', async () => {
    const seen = []
    queryHandler((body) => {
      seen.push(body.question)
      return { answer: `routed: ${body.question}`, data: {} }
    })
    const user = userEvent.setup()
    render(<RiskQuery portfolio={demoPortfolio} />)

    for (const prompt of EXAMPLES) {
      expect(screen.getByRole('button', { name: prompt })).toBeInTheDocument()
    }

    await user.click(screen.getByRole('button', { name: 'Show USD 10Y KR-DV01.' }))
    await waitFor(() => expect(seen).toEqual(['Show USD 10Y KR-DV01.']))
    expect(screen.getByRole('textbox')).toHaveValue('Show USD 10Y KR-DV01.')

    await user.click(screen.getByRole('button', { name: 'Top contributors?' }))
    await waitFor(() => expect(seen).toEqual([
      'Show USD 10Y KR-DV01.',
      'Top contributors?',
    ]))
    expect(screen.getByRole('textbox')).toHaveValue('Top contributors?')
  })

  it('renders card and provenance fields copied from the payload only', async () => {
    queryHandler(() => ({
      answer: 'USD 10Y KR-DV01 is −8 per_bp from the rates showcase.',
      data: {
        card: {
          metric: 'key_rate_dv01',
          value: -8,
          unit: 'per_bp',
          as_of: '2024-06-15',
        },
        provenance: {
          metric: 'key_rate_dv01',
          unit: 'per_bp',
          market_snapshot_id: 'snap-grounded',
        },
      },
    }))
    const user = userEvent.setup()
    render(<RiskQuery portfolio={demoPortfolio} />)
    await user.click(screen.getByRole('button', { name: 'Show USD 10Y KR-DV01.' }))

    const card = await screen.findByTestId('risk-query-result-card')
    expect(card).toHaveTextContent('key_rate_dv01')
    expect(card).toHaveTextContent('−8')
    expect(card).toHaveTextContent('per_bp')
    expect(card).toHaveTextContent('2024-06-15')
    expect(card).not.toHaveTextContent('not on this payload')
    expect(card).not.toHaveTextContent('Sign')
    expect(card).not.toHaveTextContent('Run')

    const provenance = screen.getByTestId('risk-query-provenance')
    expect(provenance).toHaveTextContent('key_rate_dv01')
    expect(provenance).toHaveTextContent('per_bp')
    expect(provenance).toHaveTextContent('snap-grounded')
    expect(provenance).not.toHaveTextContent('not on this payload')
    expect(provenance).not.toHaveTextContent('Value')

    expect(card).not.toHaveTextContent('11')
    expect(screen.getByTestId('risk-query-answer')).toHaveTextContent(
      /USD 10Y KR-DV01 is −8 per_bp from the rates showcase/,
    )
    expect(screen.queryByTestId('risk-query-assistant-state')).not.toBeInTheDocument()
    expect(screen.queryByTestId('risk-query-assistant-fallback')).not.toBeInTheDocument()
  })

  it('formats answers with bold numbers and paragraph structure', async () => {
    queryHandler(() => ({
      answer: 'Worst stress scenario is Dot-com-style equity crash with loss 677,747. Second sentence stays separate.',
      data: {},
    }))
    const user = userEvent.setup()
    render(<RiskQuery portfolio={demoPortfolio} />)
    await user.click(screen.getByRole('button', { name: 'Top contributors?' }))

    const answer = await screen.findByTestId('risk-query-answer')
    expect(answer.querySelectorAll('.query-answer-p')).toHaveLength(2)
    expect(answer.querySelector('.query-answer-lead')).toHaveTextContent(/Worst stress scenario/i)
    expect(answer.querySelector('.query-answer-num')).toHaveTextContent('677,747')
  })

  it('hides result card when every identity field is missing on the payload', async () => {
    queryHandler(() => ({
      answer: 'Worst stress scenario is Dot-com-style equity crash with loss 677,747.',
      data: {
        card: {
          metric: 'not on this payload',
          value: 'not on this payload',
          unit: 'not on this payload',
        },
        provenance: {
          metric: 'not on this payload',
          methodology: 'not on this payload',
        },
      },
    }))
    const user = userEvent.setup()
    render(<RiskQuery portfolio={demoPortfolio} />)
    await user.click(screen.getByRole('button', { name: 'Top contributors?' }))

    expect(await screen.findByTestId('risk-query-answer')).toHaveTextContent(/Worst stress scenario/)
    expect(screen.queryByTestId('risk-query-result-card')).not.toBeInTheDocument()
    expect(screen.queryByTestId('risk-query-provenance')).not.toBeInTheDocument()
    expect(screen.queryByText('not on this payload')).not.toBeInTheDocument()
  })

  it('shows a subtle AI-routed label when assistant metadata is present', async () => {
    queryHandler(() => ({
      answer: 'Top contributors from the portfolio.',
      data: {
        assistant: {
          provider: 'openai',
          model: 'gpt-test',
          mode: 'model-routed',
          fallback: false,
        },
      },
    }))
    const user = userEvent.setup()
    render(<RiskQuery portfolio={demoPortfolio} />)
    await user.click(screen.getByRole('button', { name: 'Top contributors?' }))

    const state = await screen.findByTestId('risk-query-assistant-state')
    expect(state).toHaveTextContent('AI-routed')
    expect(screen.queryByTestId('risk-query-assistant-fallback')).not.toBeInTheDocument()
    expect(screen.queryByText('gpt-test')).not.toBeInTheDocument()
  })

  it('shows a deterministic fallback note when assistant metadata reports fallback', async () => {
    queryHandler(() => ({
      answer: 'Worst stress scenario from deterministic routing.',
      data: {
        assistant: {
          provider: 'openai',
          model: 'gpt-test',
          mode: 'fallback',
          fallback: true,
        },
      },
    }))
    const user = userEvent.setup()
    render(<RiskQuery portfolio={demoPortfolio} />)
    await user.click(screen.getByRole('button', { name: 'Run equity-down stress.' }))

    const note = await screen.findByTestId('risk-query-assistant-fallback')
    expect(note).toHaveTextContent(/Deterministic fallback/i)
    expect(note).toHaveTextContent(/built-in router/i)
    expect(screen.queryByTestId('risk-query-assistant-state')).not.toBeInTheDocument()
    expect(screen.queryByText('gpt-test')).not.toBeInTheDocument()
  })

  it('shows the server clarification for Why did VaR change? without inventing digits', async () => {
    queryHandler((body) => {
      expect(body.question).toBe('Why did VaR change?')
      return {
        answer: 'Provide two completed RiskRun identifiers to explain why the risk metric changed. Do not invent VaR.',
        requires_clarification: true,
        data: { tool_result: null },
      }
    })
    const user = userEvent.setup()
    render(<RiskQuery portfolio={demoPortfolio} />)
    await user.click(screen.getByRole('button', { name: 'Why did VaR change?' }))

    const answer = await screen.findByTestId('risk-query-answer')
    expect(answer).toHaveTextContent(/Provide two completed RiskRun identifiers/i)
    expect(answer.textContent).not.toMatch(/\d/)
    expect(screen.queryByTestId('risk-query-result-card')).not.toBeInTheDocument()
  })
})
