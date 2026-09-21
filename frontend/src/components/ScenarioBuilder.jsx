import { useRef, useState } from 'react'
import {
  askRisk, compareHedge, evaluateCustomScenario, reverseStress, reverseStressMulti,
} from '../api'
import BlockHelp from './BlockHelp'
import {
  REVERSE_MULTI_FACTORS, SCENARIO_PRESETS, defaultHedgeScenarios, defaultReverseMultiForm,
  defaultScenarioForm, formatFactorShock, hedgeComparisonSummary, money, percent,
  reverseMultiRequestBody, reverseStressMultiSummary, scenarioPayload, spyFlatHedgePortfolio,
  validateReverseMultiForm, validateScenarioForm,
} from '../lib/risk.mjs'

const HEDGE_METHODS = ['LINEAR', 'DELTA_GAMMA', 'FULL_REVALUATION']

/**
 * M8.4: Scenario Builder — equity/rates/FX/vol shocks via stress evaluate API.
 * Display units → scenarioPayload (formal ScenarioWire); no client risk math.
 */
export function ScenarioBuilder({ portfolio }) {
  const [form, setForm] = useState(defaultScenarioForm)
  const [presetId, setPresetId] = useState('equity_crash')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value })

  function applyPreset(id) {
    const p = SCENARIO_PRESETS.find((x) => x.id === id)
    setPresetId(id)
    if (p) setForm({ ...p.form })
  }

  async function run() {
    if (!portfolio) return
    const check = validateScenarioForm(form)
    if (!check.ok) {
      setError(check.error)
      setResult(null)
      return
    }
    setLoading(true)
    setError('')
    try {
      const r = await evaluateCustomScenario(portfolio, scenarioPayload(form, portfolio))
      setResult(r.evaluations?.[0] ?? null)
      if (!r.evaluations?.length) setError('No evaluation returned')
    } catch (e) {
      setError(e.message || 'Scenario evaluation failed')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  const payloadPreview = validateScenarioForm(form).ok ? scenarioPayload(form, portfolio) : null
  const equityAmt = payloadPreview?.shocks?.find((s) => s.factor_type === 'equity')?.amount
  const volAmt = payloadPreview?.shocks?.find((s) => s.factor_type === 'vol')?.amount
  const rateAmt = payloadPreview?.shocks?.find((s) => s.factor_type === 'rate')?.amount
  const fxAmt = payloadPreview?.shocks?.find((s) => s.factor_type === 'fx')?.amount

  return (
    <div className="card wide">
      <div className="block-title">
        <h3>Scenario Builder</h3>
        <BlockHelp id="scenario-builder" />
      </div>
      <div className="muted">
        Custom factor shocks → POST /api/v1/risk/stress/formal/evaluate/custom (full reval on server)
      </div>
      <div className="scenario-presets" role="group" aria-label="scenario presets">
        {SCENARIO_PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`scenario-preset${presetId === p.id ? ' active' : ''}`}
            onClick={() => applyPreset(p.id)}
            disabled={loading}
          >
            {p.label}
          </button>
        ))}
      </div>
      <div className="scenario-form">
        <input
          value={form.name}
          onChange={set('name')}
          aria-label="scenario name"
          disabled={loading}
        />
        <label>
          Equity %
          <input type="number" value={form.equity} onChange={set('equity')} disabled={loading} />
        </label>
        <label>
          Vol %
          <input type="number" value={form.vol} onChange={set('vol')} disabled={loading} />
        </label>
        <label>
          Rates bp
          <input type="number" value={form.rates} onChange={set('rates')} disabled={loading} />
        </label>
        <label>
          FX %
          <input type="number" value={form.fx} onChange={set('fx')} disabled={loading} />
        </label>
        <label>
          Loss limit %
          <input type="number" value={form.limit} onChange={set('limit')} disabled={loading} />
        </label>
        <button type="button" onClick={run} disabled={!portfolio || loading}>
          {loading ? 'Running…' : 'Run scenario'}
        </button>
      </div>
      {payloadPreview && (
        <details className="tech-details scenario-payload-preview" data-testid="scenario-api-payload">
          <summary>API payload</summary>
          <p className="muted foot">
            API shocks: equity {equityAmt ?? '—'} · vol {volAmt ?? '—'}
            {' · '}rates {rateAmt != null ? `${rateAmt} (decimal)` : '—'}
            {' · '}fx {fxAmt ?? '—'}
            {' · '}max loss {percent(payloadPreview.max_loss_pct)}
            {' · '}{payloadPreview.shocks.length} factor(s)
          </p>
        </details>
      )}
      {error && <div className="error risk-run-error">{error}</div>}
      {!result && !error && <div className="muted foot">No scenario run yet</div>}
      {result && (
        <div className="scenario-result">
          <strong>{result.scenario}</strong>
          <span>Loss {money(result.loss)}</span>
          <span>{percent(result.loss_pct_nav)} NAV</span>
          <span className={`threat ${String(result.threat_level).toLowerCase()}`}>
            {result.threat_level}{result.breached ? ' / BREACH' : ''}
          </span>
        </div>
      )}
    </div>
  )
}

export function ReverseStress({ portfolio }) {
  const [factor, setFactor] = useState('equity')
  const [target, setTarget] = useState(5)
  const [result, setResult] = useState(null)
  return (
    <div className="card" data-testid="reverse-stress">
      <div className="block-title">
        <h3>Reverse Stress</h3>
        <BlockHelp id="reverse-stress" />
      </div>
      <div className="inline-form">
        <select value={factor} onChange={(e) => setFactor(e.target.value)}>
          <option>equity</option>
          <option>rates</option>
          <option>vol</option>
          <option>fx</option>
        </select>
        <input type="number" value={target} onChange={(e) => setTarget(e.target.value)} />
        <span className="muted">% target loss</span>
        <button
          type="button"
          onClick={async () => setResult(await reverseStress(portfolio, factor, Number(target) / 100))}
        >
          Solve
        </button>
      </div>
      {result && (
        <p>
          {result.converged
            ? `Required ${factor} shock: ${factor === 'rates' ? `${result.required_shock.toFixed(0)} bp` : percent(result.required_shock)}`
            : 'Target not reached within search bound.'}
        </p>
      )}
    </div>
  )
}

/**
 * Multi-factor reverse stress — POST /api/v1/risk/stress/reverse/multi.
 * Displays MultiFactorReverseStressResult only; no client search/optimization.
 */
export function ReverseStressMulti({ portfolio }) {
  const [form, setForm] = useState(defaultReverseMultiForm)
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  function toggleFactor(factor) {
    setForm({
      ...form,
      factors: { ...form.factors, [factor]: !form.factors[factor] },
    })
  }

  function setWeight(factor, value) {
    setForm({ ...form, weights: { ...form.weights, [factor]: value } })
  }

  async function run() {
    if (!portfolio) return
    const check = validateReverseMultiForm(form)
    if (!check.ok) {
      setError(check.error)
      setSummary(null)
      return
    }
    setLoading(true)
    setError('')
    try {
      const body = reverseMultiRequestBody(form)
      const result = await reverseStressMulti(portfolio, body.target_loss_pct, {
        factors: body.factors,
        weights: body.weights,
        max_shock: body.max_shock,
      })
      setSummary(reverseStressMultiSummary(result))
    } catch (e) {
      setError(e.message || 'Multi-factor reverse stress failed')
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card wide" data-testid="reverse-stress-multi">
      <div className="block-title">
        <h3>Multi-Factor Reverse Stress</h3>
        <BlockHelp id="reverse-stress-multi" />
      </div>
      <div className="muted">
        Constrained joint adverse moves → POST /api/v1/risk/stress/reverse/multi
        (server ray search + coordinate descent; not a certified global optimum)
      </div>
      <div className="reverse-multi-factors" role="group" aria-label="reverse multi factors">
        {REVERSE_MULTI_FACTORS.map((f) => (
          <label key={f} className="reverse-multi-factor">
            <input
              type="checkbox"
              checked={!!form.factors[f]}
              onChange={() => toggleFactor(f)}
              disabled={loading}
              aria-label={`factor ${f}`}
            />
            {f}
          </label>
        ))}
      </div>
      <div className="inline-form risk-run-form reverse-multi-form">
        <label>
          Target loss %
          <input
            type="number"
            value={form.target_loss_pct}
            onChange={(e) => setForm({ ...form, target_loss_pct: e.target.value })}
            disabled={loading}
            aria-label="multi reverse target loss percent"
          />
        </label>
        <label>
          Max shock %
          <input
            type="number"
            value={form.max_shock}
            onChange={(e) => setForm({ ...form, max_shock: e.target.value })}
            disabled={loading}
            aria-label="multi reverse max shock percent"
          />
        </label>
        {REVERSE_MULTI_FACTORS.filter((f) => form.factors[f]).map((f) => (
          <label key={`w-${f}`}>
            Weight {f}
            <input
              type="number"
              value={form.weights[f]}
              onChange={(e) => setWeight(f, e.target.value)}
              disabled={loading}
              placeholder="equal"
              aria-label={`weight ${f}`}
            />
          </label>
        ))}
        <button type="button" onClick={run} disabled={!portfolio || loading}>
          {loading ? 'Solving…' : 'Solve multi-factor'}
        </button>
      </div>
      {error && <div className="error risk-run-error">{error}</div>}
      {!summary && !error && (
        <div className="muted foot">No multi-factor reverse run yet</div>
      )}
      {summary && (
        <div className="risk-panel-result reverse-multi-result">
          <div className="attribution-total">
            <span>
              Status{' '}
              <strong className={summary.converged ? 'positive' : 'negative'}>
                {summary.converged ? 'Converged' : 'Not converged'}
              </strong>
            </span>
            <span>Target {percent(summary.target_loss_pct ?? 0)}</span>
            <span>Achieved {percent(summary.achieved_loss_pct ?? 0)}</span>
            <span className={(summary.pnl ?? 0) < 0 ? 'negative' : 'positive'}>
              P&amp;L {money(summary.pnl ?? 0)}
            </span>
            {summary.method && <span className="muted">{summary.method}</span>}
            {summary.iterations != null && (
              <span className="muted">{summary.iterations} iter</span>
            )}
          </div>
          {summary.message && <div className="muted foot">{summary.message}</div>}
          {summary.shocks.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Factor</th>
                  <th>Required shock</th>
                  <th>Unit</th>
                  <th>Weight</th>
                </tr>
              </thead>
              <tbody>
                {summary.shocks.map((s) => (
                  <tr key={s.factor}>
                    <td>{s.factor}</td>
                    <td>{formatFactorShock(s)}</td>
                    <td className="muted">{s.shock_unit}</td>
                    <td>{s.weight == null ? '—' : Number(s.weight).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {summary.assumptions.length > 0 && (
            <ul className="muted foot reverse-multi-assumptions">
              {summary.assumptions.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

const RISK_QUERY_EXAMPLES = [
  'Why did VaR change?',
  'Top contributors?',
  'Show USD 10Y KR-DV01.',
  'Run equity-down stress.',
  'Compare these RiskRuns.',
]

const MISSING_ON_PAYLOAD = 'not on this payload'

const RISK_QUERY_CARD_FIELDS = [
  ['metric', 'Metric'],
  ['value', 'Value'],
  ['unit', 'Unit'],
  ['sign_convention', 'Sign'],
  ['risk_run_id', 'Run'],
  ['as_of', 'As of'],
]

const RISK_QUERY_PROVENANCE_FIELDS = [
  ['metric', 'Metric'],
  ['value', 'Value'],
  ['unit', 'Unit'],
  ['sign_convention', 'Sign'],
  ['risk_run_id', 'Run'],
  ['as_of', 'As of'],
  ['methodology', 'Methodology'],
  ['market_snapshot_id', 'Snapshot'],
]

function copiedQueryField(source, key) {
  if (!source || !Object.prototype.hasOwnProperty.call(source, key)) {
    return null
  }
  const value = source[key]
  if (value == null || value === '' || value === MISSING_ON_PAYLOAD) return null
  if (typeof value === 'object') return null
  if (typeof value === 'number') return String(value).replace('-', '−')
  return String(value)
}

function presentQueryFields(source, fields) {
  return fields
    .map(([key, label]) => {
      const value = copiedQueryField(source, key)
      return value == null ? null : [key, label, value]
    })
    .filter(Boolean)
}

function QueryFieldList({ title, source, fields, testId }) {
  const rows = presentQueryFields(source, fields)
  if (!rows.length) return null
  return (
    <section className="risk-query-fields" data-testid={testId} id={testId}>
      <h4>{title}</h4>
      <dl>
        {rows.map(([key, label, value]) => (
          <div key={key} className="risk-query-field">
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function hasCopiedObject(value) {
  return value != null && typeof value === 'object' && !Array.isArray(value) && Object.keys(value).length > 0
}

function isRiskQueryAssistantMeta(value) {
  return (
    value != null
    && typeof value === 'object'
    && !Array.isArray(value)
    && typeof value.provider === 'string'
    && typeof value.mode === 'string'
    && typeof value.fallback === 'boolean'
  )
}

/** Split deterministic answer text into sentences for readable paragraphs. */
export function splitRiskQueryParagraphs(answer) {
  const text = String(answer || '').trim()
  if (!text) return []
  // Break on ". " only — never on decimal points inside values like 12.1%.
  const chunks = text.split(/\.\s+/).map((part) => part.trim()).filter(Boolean)
  if (chunks.length <= 1) return [text]
  return chunks.map((part, index) => {
    if (/[.!?]$/.test(part)) return part
    return index < chunks.length - 1 || /\.\s*$/.test(text) ? `${part}.` : part
  })
}

function boldRiskQueryNumbers(text) {
  const parts = String(text).split(/([−-]?\d[\d,]*(?:\.\d+)?%?)/g)
  return parts.map((part, index) => (
    /^[−-]?\d/.test(part)
      ? <strong key={`n-${index}`} className="query-answer-num">{part}</strong>
      : part
  ))
}

function formatRiskQueryInline(paragraph) {
  const match = String(paragraph).match(/^(.+?)\s+(is|are|from)\s+(.+)$/i)
  if (!match) return boldRiskQueryNumbers(paragraph)
  return (
    <>
      <strong className="query-answer-lead">{boldRiskQueryNumbers(match[1])}</strong>
      {` ${match[2]} `}
      {boldRiskQueryNumbers(match[3])}
    </>
  )
}

function RiskQueryAnswer({ answer, testId = 'risk-query-answer' }) {
  const paragraphs = splitRiskQueryParagraphs(answer)
  if (!paragraphs.length) return null
  return (
    <div className="query-answer" data-testid={testId}>
      {paragraphs.map((paragraph, index) => (
        <p key={`p-${index}`} className="query-answer-p">
          {formatRiskQueryInline(paragraph)}
        </p>
      ))}
    </div>
  )
}

function RiskQueryAssistantState({ assistant }) {
  if (!isRiskQueryAssistantMeta(assistant)) return null
  if (assistant.fallback || assistant.mode === 'fallback') {
    return (
      <p
        className="muted foot"
        data-testid="risk-query-assistant-fallback"
        role="note"
      >
        Deterministic fallback — AI routing was unavailable; this answer uses the built-in router.
      </p>
    )
  }
  const label = (
    assistant.mode === 'model-narrated'
      ? 'AI-narrated'
      : assistant.mode === 'model-routed'
        ? 'AI-routed'
        : assistant.mode === 'preflight-refused'
          ? 'Request refused'
          : null
  )
  if (!label) return null
  return (
    <p className="eyebrow" data-testid="risk-query-assistant-state">
      {label}
    </p>
  )
}

function RiskQueryToolActivity({ turns }) {
  if (!Array.isArray(turns) || turns.length === 0) return null
  return (
    <div className="risk-query-tools" data-testid="risk-query-tool-activity">
      {turns.map((turn, index) => {
        const name = String(turn?.tool_name || 'tool')
        const status = String(turn?.status || 'unknown')
        const payload = turn?.result ?? turn?.error ?? null
        return (
          <details key={`${name}-${index}`} className="risk-query-tool">
            <summary>
              <span>{name}</span>
              <span className="muted"> {status}</span>
              {hasCopiedObject(turn?.provenance) ? (
                <a className="risk-query-tool-provenance" href="#risk-query-provenance">
                  Provenance
                </a>
              ) : null}
            </summary>
            {payload != null && (
              <pre className="risk-query-tool-result">{JSON.stringify(payload, null, 2)}</pre>
            )}
          </details>
        )
      })}
    </div>
  )
}

function isAbortError(error) {
  return error?.name === 'AbortError' || error?.code === 20
}

export function RiskQuery({ portfolio }) {
  const [q, setQ] = useState('What is the worst stress scenario?')
  const [r, setR] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [cancelled, setCancelled] = useState(false)
  const [messages, setMessages] = useState([])
  const [conversationId, setConversationId] = useState(null)
  const [lastQuestion, setLastQuestion] = useState('')
  const abortRef = useRef(null)

  function resetConversation() {
    abortRef.current?.abort()
    abortRef.current = null
    setMessages([])
    setConversationId(null)
    setR(null)
    setError('')
    setCancelled(false)
    setLastQuestion('')
    setBusy(false)
  }

  async function submit(question) {
    const text = String(question || '').trim()
    if (!text || busy) return
    setQ(text)
    setLastQuestion(text)
    setBusy(true)
    setError('')
    setCancelled(false)
    setMessages((current) => {
      const last = current[current.length - 1]
      if (last?.role === 'user') {
        if (last.text === text) return current
        return [...current.slice(0, -1), { role: 'user', text }]
      }
      return [...current, { role: 'user', text }]
    })
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const response = await askRisk(portfolio, text, {
        conversationId,
        signal: controller.signal,
      })
      const nextId = response?.data?.conversation_id || conversationId
      if (nextId) setConversationId(nextId)
      setR(response)
      setMessages((current) => [
        ...current,
        {
          role: 'assistant',
          answer: response?.answer || '',
          data: response?.data || {},
          requiresClarification: Boolean(response?.requires_clarification),
        },
      ])
    } catch (e) {
      if (isAbortError(e)) {
        setCancelled(true)
        setMessages((current) => current.slice(0, -1))
      } else {
        setR(null)
        setError(e.message || 'Query failed')
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null
      setBusy(false)
    }
  }

  const card = r?.data?.card
  const provenance = r?.data?.provenance
  const assistant = r?.data?.assistant
  const truncated = Boolean(r?.data?.investigation?.truncated)
  const lastAssistantIndex = [...messages].reverse().findIndex((m) => m.role === 'assistant')
  const lastAssistantAbs = lastAssistantIndex === -1 ? -1 : messages.length - 1 - lastAssistantIndex

  return (
    <div className="card risk-query-panel" data-testid="golden-demo-risk-query">
      <div className="block-title">
        <h3>Risk Query</h3>
        <BlockHelp id="risk-query" />
      </div>
      <div className="query-examples" data-testid="risk-query-examples">
        {RISK_QUERY_EXAMPLES.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="query-example"
            disabled={busy}
            onClick={() => submit(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
      <div className="query">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault()
              submit(q)
            }
          }}
          aria-label="Risk question"
          disabled={busy}
        />
        <button type="button" disabled={busy} onClick={() => submit(q)}>
          {busy ? 'Asking…' : 'Ask'}
        </button>
        {busy && (
          <button type="button" onClick={() => abortRef.current?.abort()}>
            Cancel
          </button>
        )}
        {!busy && error && lastQuestion && (
          <button type="button" onClick={() => submit(lastQuestion)}>
            Retry
          </button>
        )}
        {!busy && truncated && (
          <button type="button" onClick={() => submit(lastQuestion)}>
            Retry
          </button>
        )}
        <button type="button" onClick={resetConversation} disabled={busy}>
          New conversation
        </button>
      </div>
      {busy && (
        <div className="risk-query-waiting" data-testid="risk-query-waiting" role="status" aria-live="polite">
          <span className="risk-query-spinner" aria-hidden="true" />
          <span>Waiting for risk answer…</span>
        </div>
      )}
      {cancelled && (
        <p className="muted" data-testid="risk-query-cancelled" role="status">
          Request cancelled.
        </p>
      )}
      {error && <p className="error" data-testid="risk-query-error">{error}</p>}
      {truncated && (
        <p className="muted" data-testid="risk-query-partial" role="status">
          Partial result — the investigation stopped before a final answer.
        </p>
      )}
      {messages.length > 0 && (
        <ol className="risk-query-transcript" data-testid="risk-query-transcript" aria-label="Conversation">
          {messages.map((message, index) => (
            <li
              key={`${message.role}-${index}`}
              className={`risk-query-turn risk-query-turn-${message.role}`}
            >
              <span className="eyebrow">{message.role === 'user' ? 'You' : 'Assistant'}</span>
              {message.role === 'user' ? (
                <p>{message.text}</p>
              ) : (
                <>
                  <RiskQueryAssistantState assistant={message.data?.assistant} />
                  <RiskQueryAnswer
                    answer={message.answer}
                    testId={index === lastAssistantAbs ? 'risk-query-answer' : undefined}
                  />
                  <RiskQueryToolActivity turns={message.data?.investigation?.turns} />
                </>
              )}
            </li>
          ))}
        </ol>
      )}
      {!busy && r && messages.length === 0 && (
        <div className="query-result">
          <RiskQueryAssistantState assistant={assistant} />
          <RiskQueryAnswer answer={r.answer} />
        </div>
      )}
      {hasCopiedObject(card) && (
        <QueryFieldList
          title="Result card"
          source={card}
          fields={RISK_QUERY_CARD_FIELDS}
          testId="risk-query-result-card"
        />
      )}
      {hasCopiedObject(provenance) && (
        <QueryFieldList
          title="Provenance"
          source={provenance}
          fields={RISK_QUERY_PROVENANCE_FIELDS}
          testId="risk-query-provenance"
        />
      )}
      <div className="muted">
        Ask in plain language. With AI enabled the model only picks a tool; numbers stay
        deterministic. “Why did VaR change?” needs two completed RiskRun ids and never
        invents VaR.
      </div>
    </div>
  )
}

/**
 * M8.5: before/after hedge workflow. Displays HedgeComparisonReport from API only.
 * Demo hedge = SPY equity flat (qty 0); default scenario = equity Crash −20%.
 */
export function HedgeCompare({ portfolio }) {
  const [methodology, setMethodology] = useState('DELTA_GAMMA')
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function run() {
    if (!portfolio) return
    setLoading(true)
    setError('')
    try {
      const hedged = spyFlatHedgePortfolio(portfolio)
      const report = await compareHedge(portfolio, hedged, defaultHedgeScenarios(portfolio), methodology)
      setSummary(hedgeComparisonSummary(report))
    } catch (e) {
      setError(e.message || 'Hedge compare failed')
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card wide" data-testid="golden-demo-hedge">
      <div className="block-title">
        <h3>Hedge Compare</h3>
        <BlockHelp id="hedge-compare" />
      </div>
      <div className="muted">
        Before/after SPY flat hedge — VaR, ES, scenario P&amp;L, and factor deltas from API (no client risk math)
      </div>
      <div className="inline-form risk-run-form">
        <select
          value={methodology}
          onChange={(e) => setMethodology(e.target.value)}
          aria-label="hedge methodology"
          disabled={loading}
        >
          {HEDGE_METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <button type="button" onClick={run} disabled={!portfolio || loading}>
          {loading ? 'Comparing…' : 'Compare hedge'}
        </button>
      </div>
      {error && <div className="error risk-run-error">{error}</div>}
      {!summary && !error && <div className="muted foot">No comparison run yet</div>}
      {summary && (
        <div className="hedge-compare-result" data-testid="golden-demo-hedge-result">
          <div className="attribution-total">
            <span>Hedge cost <strong>{money(summary.hedge_cost ?? 0)}</strong></span>
            <span>
              99% VaR {money(summary.base_var_99 ?? 0)} → {money(summary.hedged_var_99 ?? 0)}
              {' '}(
              <span className={(summary.var_improvement ?? 0) >= 0 ? 'positive' : 'negative'}>
                Δ {money(summary.var_improvement ?? 0)}
              </span>
              )
            </span>
            <span>
              99% ES {money(summary.base_expected_shortfall_99 ?? 0)} → {money(summary.hedged_expected_shortfall_99 ?? 0)}
              {' '}(
              <span className={(summary.es_improvement ?? 0) >= 0 ? 'positive' : 'negative'}>
                Δ {money(summary.es_improvement ?? 0)}
              </span>
              )
            </span>
            {summary.methodology && <span className="muted">{summary.methodology}</span>}
          </div>
          {summary.scenarios.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Scenario</th>
                  <th>Base P&amp;L</th>
                  <th>Hedged P&amp;L</th>
                  <th>Improvement</th>
                  <th>Loss Δ</th>
                </tr>
              </thead>
              <tbody>
                {summary.scenarios.map((row) => (
                  <tr key={row.scenario}>
                    <td>{row.scenario}</td>
                    <td className={(row.base_pnl ?? 0) < 0 ? 'negative' : 'positive'}>{money(row.base_pnl ?? 0)}</td>
                    <td className={(row.hedged_pnl ?? 0) < 0 ? 'negative' : 'positive'}>{money(row.hedged_pnl ?? 0)}</td>
                    <td className={(row.improvement ?? 0) < 0 ? 'negative' : 'positive'}>{money(row.improvement ?? 0)}</td>
                    <td className={(row.loss_improvement ?? 0) < 0 ? 'negative' : 'positive'}>
                      {money(row.loss_improvement ?? 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {summary.factor_exposure_changes.length > 0 && (
            <>
              <div className="muted foot">Factor exposure changes</div>
              <table>
                <thead><tr><th>Factor</th><th>Before</th><th>After</th><th>Δ</th></tr></thead>
                <tbody>
                  {summary.factor_exposure_changes.map((f) => (
                    <tr key={f.factor}>
                      <td>{f.factor}</td>
                      <td>{money(f.before ?? 0)}</td>
                      <td>{money(f.after ?? 0)}</td>
                      <td className={(f.delta ?? 0) < 0 ? 'negative' : 'positive'}>{money(f.delta ?? 0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
    </div>
  )
}
