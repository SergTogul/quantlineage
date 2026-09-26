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

  it('keeps decimal percentages intact for top contributors answers', async () => {
    queryHandler(() => ({
      answer: 'Top risk contributors: eq-nvda 25.1%, eq-aapl 18.0%, eq-msft 12.5%.',
      data: {},
    }))
    const user = userEvent.setup()
    render(<RiskQuery portfolio={demoPortfolio} />)
    await user.click(screen.getByRole('button', { name: 'Top contributors?' }))

    const answer = await screen.findByTestId('risk-query-answer')
    expect(answer.querySelectorAll('.query-answer-p')).toHaveLength(1)
    expect(answer).toHaveTextContent('Top risk contributors: eq-nvda 25.1%, eq-aapl 18.0%, eq-msft 12.5%.')
    expect(answer.querySelectorAll('.query-answer-num')).toHaveLength(3)
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

  it('shows a waiting spinner while the risk query is in flight', async () => {
    let resolveRequest
    const pending = new Promise((resolve) => {
      resolveRequest = resolve
    })
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/query`, async () => {
        await pending
        return HttpResponse.json({
          answer: 'Top risk contributors: eq-nvda 25.1%.',
          data: {},
        })
      }),
    )
    const user = userEvent.setup()
    render(<RiskQuery portfolio={demoPortfolio} />)

    await user.click(screen.getByRole('button', { name: 'Top contributors?' }))

    expect(await screen.findByTestId('risk-query-waiting')).toHaveTextContent(/Waiting for risk answer/i)
    expect(screen.getByRole('button', { name: 'Asking…' })).toBeDisabled()
    expect(screen.queryByTestId('risk-query-answer')).not.toBeInTheDocument()

    resolveRequest()

    expect(await screen.findByTestId('risk-query-answer')).toHaveTextContent(/Top risk contributors/)
    expect(screen.queryByTestId('risk-query-waiting')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ask' })).toBeEnabled()
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
    expect(screen.queryByTestId('risk-query-error')).not.toBeInTheDocument()
    expect(screen.getByTestId('risk-query-transcript')).toHaveTextContent(/Why did VaR change\?/)
  })

  it('renders a transcript, keeps conversation_id, and compact tool activity', async () => {
    const seen = []
    queryHandler((body) => {
      seen.push(body)
      if (!body.conversation_id) {
        return {
          answer: 'Options delta ranking was calculated by QuantLineage.',
          data: {
            conversation_id: 'conv_ui_1',
            assistant: { provider: 'openai', model: 'gpt-test', mode: 'model-narrated', fallback: false },
            investigation: {
              rounds_used: 2,
              stopped_reason: 'final',
              tool_names: ['get_position_greeks'],
              turns: [
                {
                  tool_name: 'get_position_greeks',
                  tool_args: { greek: 'delta', options_only: true },
                  status: 'success',
                  result: { greek: 'delta', positions: [{ position_id: 'opt-1', value: 12 }] },
                  grounding_manifest: [],
                  provenance: { portfolio_id: 'demo' },
                },
              ],
            },
          },
        }
      }
      return {
        answer: 'Options gamma ranking was calculated by QuantLineage.',
        data: {
          conversation_id: body.conversation_id,
          assistant: { provider: 'openai', model: 'gpt-test', mode: 'model-narrated', fallback: false },
          investigation: {
            rounds_used: 2,
            stopped_reason: 'final',
            tool_names: ['get_position_greeks'],
            turns: [
              {
                tool_name: 'get_position_greeks',
                tool_args: { greek: 'gamma', options_only: true },
                status: 'success',
                result: { greek: 'gamma', positions: [{ position_id: 'opt-1', value: 0.4 }] },
                grounding_manifest: [],
                provenance: { portfolio_id: 'demo' },
              },
            ],
          },
        },
      }
    })
    const user = userEvent.setup()
    render(<RiskQuery portfolio={demoPortfolio} />)

    await user.click(screen.getByRole('button', { name: 'Top contributors?' }))
    expect(await screen.findByTestId('risk-query-transcript')).toHaveTextContent('Top contributors?')
    expect(screen.getByTestId('risk-query-assistant-state')).toHaveTextContent('AI-narrated')
    expect(screen.getByTestId('risk-query-tool-activity')).toHaveTextContent('get_position_greeks')
    expect(screen.getByTestId('risk-query-tool-activity')).toHaveTextContent(/success/i)
    expect(screen.queryByText(/supported_tools/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/chain.of.thought/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/sk-secret/i)).not.toBeInTheDocument()
    expect(screen.queryByText('gpt-test')).not.toBeInTheDocument()

    await user.clear(screen.getByRole('textbox', { name: 'Risk question' }))
    await user.type(screen.getByRole('textbox', { name: 'Risk question' }), 'What about gamma?')
    await user.keyboard('{Enter}')

    await waitFor(() => expect(seen).toHaveLength(2))
    expect(seen[1].conversation_id).toBe('conv_ui_1')
    expect(seen[1].question).toBe('What about gamma?')
    const transcript = screen.getByTestId('risk-query-transcript')
    expect(transcript).toHaveTextContent('Top contributors?')
    expect(transcript).toHaveTextContent('What about gamma?')
    expect(transcript).toHaveTextContent(/gamma ranking/i)
  })

  it('New conversation clears local state so the next ask has no conversation_id', async () => {
    const seen = []
    queryHandler((body) => {
      seen.push(body)
      return {
        answer: 'Historical VaR is 32,798.',
        data: { conversation_id: body.conversation_id || 'conv_keep' },
      }
    })
    const user = userEvent.setup()
    render(<RiskQuery portfolio={demoPortfolio} />)
    await user.click(screen.getByRole('button', { name: 'Top contributors?' }))
    await screen.findByTestId('risk-query-transcript')
    await user.click(screen.getByRole('button', { name: 'New conversation' }))
    expect(screen.queryByTestId('risk-query-transcript')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show USD 10Y KR-DV01.' }))
    await waitFor(() => expect(seen).toHaveLength(2))
    expect(seen[1].conversation_id).toBeUndefined()
  })

  it('exposes cancel, retry, and partial-result states distinctly', async () => {
    let resolveRequest
    const pending = new Promise((resolve) => {
      resolveRequest = resolve
    })
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/query`, async () => {
        await pending
        return HttpResponse.json({
          answer: 'The investigation stopped after a provider error.',
          requires_clarification: true,
          data: {
            conversation_id: 'conv_partial',
            assistant: { provider: 'openai', mode: 'fallback', fallback: true },
            investigation: { truncated: true, turns: [{ tool_name: 'get_var_es', status: 'success', tool_args: {}, result: {} }] },
          },
        })
      }),
    )
    const user = userEvent.setup()
    render(<RiskQuery portfolio={demoPortfolio} />)
    await user.click(screen.getByRole('button', { name: 'Top contributors?' }))
    expect(await screen.findByRole('button', { name: 'Cancel' })).toBeEnabled()
    resolveRequest()
    expect(await screen.findByTestId('risk-query-partial')).toHaveTextContent(/partial/i)
    expect(screen.getByTestId('risk-query-assistant-fallback')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry' })).toBeEnabled()
  })

  it('Retry after a failed ask does not duplicate the user turn in the transcript', async () => {
    let attempts = 0
    server.use(
      http.post(`${API_BASE}${API_V1}/risk/query`, async () => {
        attempts += 1
        if (attempts === 1) {
          return HttpResponse.json({ code: 'provider_error', message: 'unavailable' }, { status: 503 })
        }
        return HttpResponse.json({
          answer: 'Worst stress scenario is Dot-com-style equity crash.',
          data: { conversation_id: 'conv_retry' },
        })
      }),
    )
    const user = userEvent.setup()
    render(<RiskQuery portfolio={demoPortfolio} />)
    await user.click(screen.getByRole('button', { name: 'Ask' }))

    expect(await screen.findByTestId('risk-query-error')).toBeInTheDocument()
    const transcript = screen.getByTestId('risk-query-transcript')
    expect(transcript.querySelectorAll('.risk-query-turn-user')).toHaveLength(1)
    expect(transcript).toHaveTextContent('What is the worst stress scenario?')
    expect(transcript.querySelectorAll('.risk-query-turn-assistant')).toHaveLength(0)

    await user.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByTestId('risk-query-answer')).toHaveTextContent(/Worst stress scenario/i)
    expect(screen.queryByTestId('risk-query-error')).not.toBeInTheDocument()
    expect(attempts).toBe(2)
    expect(transcript.querySelectorAll('.risk-query-turn-user')).toHaveLength(1)
    expect(transcript.querySelectorAll('.risk-query-turn-assistant')).toHaveLength(1)
  })
})
