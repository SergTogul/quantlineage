import { useState } from 'react'
import {
  askRisk, compareHedge, evaluateCustomScenario, reverseStress, reverseStressMulti,
} from '../api'
import {
  REVERSE_MULTI_FACTORS, SCENARIO_PRESETS, defaultHedgeScenarios, defaultReverseMultiForm,
  defaultScenarioForm, formatFactorShock, hedgeComparisonSummary, money, percent,
  reverseMultiRequestBody, reverseStressMultiSummary, scenarioPayload, spyFlatHedgePortfolio,
  validateReverseMultiForm, validateScenarioForm,
} from '../lib/risk.mjs'

const HEDGE_METHODS = ['LINEAR', 'DELTA_GAMMA', 'FULL_REVALUATION']

/**
 * M8.4: Scenario Builder — equity/rates/FX/vol shocks via stress evaluate API.
 * Display units → scenarioPayload; no client risk math.
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
      const r = await evaluateCustomScenario(portfolio, scenarioPayload(form))
      setResult(r.evaluations?.[0] ?? null)
      if (!r.evaluations?.length) setError('No evaluation returned')
    } catch (e) {
      setError(e.message || 'Scenario evaluation failed')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  const payloadPreview = validateScenarioForm(form).ok ? scenarioPayload(form) : null

  return (
    <div className="card wide">
      <h3>Scenario Builder</h3>
      <div className="muted">
        Custom factor shocks → POST /api/v1/risk/stress/evaluate/custom (full reval on server)
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
        <div className="muted foot scenario-payload-preview">
          API shocks: equity {payloadPreview.equity_shock} · vol {payloadPreview.vol_shock}
          {' · '}rates {payloadPreview.rates_shift_bps} bp · fx {payloadPreview.fx_shock}
          {' · '}max loss {percent(payloadPreview.max_loss_pct)}
        </div>
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
    <div className="card">
      <h3>Reverse Stress</h3>
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
      <h3>Multi-Factor Reverse Stress</h3>
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

export function RiskQuery({ portfolio }) {
  const [q, setQ] = useState('What is the worst stress scenario?')
  const [r, setR] = useState(null)
  return (
    <div className="card">
      <h3>Risk Query</h3>
      <div className="query">
        <input value={q} onChange={(e) => setQ(e.target.value)} />
        <button type="button" onClick={async () => setR(await askRisk(portfolio, q))}>Ask</button>
      </div>
      {r && <p className="query-answer">{r.answer}</p>}
      <div className="muted">Deterministic routing to risk APIs; ready for an LLM tool layer later.</div>
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
      const report = await compareHedge(portfolio, hedged, defaultHedgeScenarios(), methodology)
      setSummary(hedgeComparisonSummary(report))
    } catch (e) {
      setError(e.message || 'Hedge compare failed')
      setSummary(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card wide">
      <h3>Hedge Compare</h3>
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
        <div className="hedge-compare-result">
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
