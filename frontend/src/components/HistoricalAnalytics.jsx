import { useEffect, useRef, useState } from 'react'
import { historicalAnalytics } from '../api.js'
import BlockHelp from './BlockHelp'
import { DatedSeriesChart } from './RiskVisuals.jsx'
import { hashForPanel, hashForSection } from '../lib/nav.mjs'
import { money } from '../lib/risk.mjs'
import DataSourceBadge from './DataSourceBadge.jsx'

const DEFAULT_START = '2024-01-02'
const DEFAULT_END = '2024-11-15'

function apiErrorText(err, fallback) {
  const code = err?.body?.code
  const message = err?.body?.message || err?.message || fallback
  return code ? `${code}: ${message}` : message
}

/** Display-only: API fraction → percent text. Not annualization. */
function formatFraction(value, digits = 2) {
  if (value == null || !Number.isFinite(Number(value))) return 'undefined'
  return `${(Number(value) * 100).toFixed(digits)}%`
}

function formatNumber(value, digits = 2) {
  if (value == null || !Number.isFinite(Number(value))) return 'undefined'
  return Number(value).toFixed(digits)
}

function buildRequest(portfolio, start, end) {
  return {
    portfolio,
    start,
    end,
    frequency: 'DAILY',
    include_benchmark: true,
  }
}

/** Result/error belong to this POST only — never show a prior range/book. */
function requestKey(portfolio, start, end) {
  if (!portfolio || !start || !end) return ''
  return `${portfolio.id}:${portfolio.version}:${start}:${end}`
}

function resultRequestKey(result) {
  if (!result) return ''
  return requestKey(
    { id: result.portfolio_id, version: result.portfolio_version },
    result.start,
    result.end,
  )
}

function Identity({ result }) {
  const ann = result.annualization || {}
  return (
    <dl className="ha-identity" data-testid="ha-identity">
      <div><dt>Portfolio</dt><dd>{result.portfolio_id} · v{result.portfolio_version}</dd></div>
      <div><dt>Dataset</dt><dd>{result.historical_dataset_id} / {result.historical_dataset_version}</dd></div>
      <div><dt>Snapshot</dt><dd>{result.market_snapshot_id || '—'}</dd></div>
      <div><dt>Range</dt><dd>{result.start} → {result.end}</dd></div>
      <div><dt>Frequency</dt><dd>{result.frequency}</dd></div>
      <div><dt>Methodology</dt><dd>{result.methodology}</dd></div>
      <div>
        <dt>Annualization</dt>
        <dd>{ann.return_method} · {ann.volatility_method} · {ann.periods_per_year}</dd>
      </div>
    </dl>
  )
}

function SummaryTable({ result }) {
  const units = result.units || {}
  return (
    <table className="ha-summary" data-testid="ha-summary">
      <thead>
        <tr><th>Metric</th><th>Value</th><th>Unit</th></tr>
      </thead>
      <tbody>
        <tr>
          <th scope="row">Cumulative return</th>
          <td>{formatFraction(result.cumulative_return)}</td>
          <td>{units.returns}</td>
        </tr>
        <tr>
          <th scope="row">Annualized return</th>
          <td>{formatFraction(result.annualized_return)}</td>
          <td>{units.returns}</td>
        </tr>
        <tr>
          <th scope="row">Annualized volatility</th>
          <td>{formatFraction(result.annualized_volatility)}</td>
          <td>{units.volatility}</td>
        </tr>
        <tr>
          <th scope="row">Max drawdown</th>
          <td>{formatFraction(result.max_drawdown)}</td>
          <td>{units.drawdown}</td>
        </tr>
        <tr>
          <th scope="row">Sharpe</th>
          <td data-testid="ha-sharpe">{result.sharpe == null ? 'undefined' : formatNumber(result.sharpe)}</td>
          <td data-testid="ha-sharpe-unit">{result.sharpe == null ? 'undefined' : '—'}</td>
        </tr>
        <tr>
          <th scope="row">Observations</th>
          <td>{result.observation_count}</td>
          <td>count</td>
        </tr>
      </tbody>
    </table>
  )
}

function BenchmarkBlock({ benchmark }) {
  if (!benchmark) return null
  const units = benchmark.units || {}
  return (
    <div className="ha-block" data-testid="ha-benchmark">
      <h3>SPY benchmark</h3>
      <p className="muted">
        SPY nested in the same analytics result — a relative comparison, not allocation advice.
      </p>
      <details className="tech-details">
        <summary>How this benchmark is nested</summary>
        <p className="muted">
          Nested <code>benchmark</code> from the same result — {benchmark.instrument_id} / {benchmark.factor_column}.
        </p>
      </details>
      <table>
        <thead>
          <tr><th>Metric</th><th>Value</th><th>Unit</th></tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Cumulative return</th>
            <td>{formatFraction(benchmark.cumulative_return)}</td>
            <td>{units.returns}</td>
          </tr>
          <tr>
            <th scope="row">Excess return</th>
            <td>{formatFraction(benchmark.excess_return)}</td>
            <td>{units.excess_return}</td>
          </tr>
          <tr>
            <th scope="row">Beta</th>
            <td>{formatNumber(benchmark.beta)}</td>
            <td>{units.beta}</td>
          </tr>
          <tr>
            <th scope="row">Tracking error</th>
            <td>{formatFraction(benchmark.tracking_error)}</td>
            <td>{units.tracking_error}</td>
          </tr>
          <tr>
            <th scope="row">Relative drawdown</th>
            <td>{formatFraction(benchmark.relative_drawdown)}</td>
            <td>{units.relative_drawdown}</td>
          </tr>
          <tr>
            <th scope="row">Correlation</th>
            <td>{formatNumber(benchmark.correlation)}</td>
            <td>{units.correlation}</td>
          </tr>
          <tr>
            <th scope="row">Aligned window</th>
            <td>{benchmark.aligned_start} → {benchmark.aligned_end}</td>
            <td>{benchmark.observation_count} obs</td>
          </tr>
        </tbody>
      </table>
      <h4>Benchmark wealth</h4>
      <DatedSeriesChart
        series={benchmark.wealth}
        unit={units.wealth}
        ariaLabel="SPY benchmark wealth"
        testId="ha-benchmark-wealth-chart"
      />
    </div>
  )
}

export default function HistoricalAnalytics({ portfolio }) {
  const [start, setStart] = useState(DEFAULT_START)
  const [end, setEnd] = useState(DEFAULT_END)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const seq = useRef(0)
  const key = requestKey(portfolio, start, end)
  const current = Boolean(result && resultRequestKey(result) === key)
  const errorCurrent = Boolean(error && error.key === key)
  const waiting = Boolean(portfolio && start && end && !current && !errorCurrent)

  useEffect(() => {
    if (!portfolio || !start || !end) return undefined
    const requestId = seq.current + 1
    seq.current = requestId
    const postedKey = requestKey(portfolio, start, end)
    let cancelled = false
    historicalAnalytics(buildRequest(portfolio, start, end))
      .then((next) => {
        if (cancelled || seq.current !== requestId) return
        setResult(next)
        setError(null)
      })
      .catch((err) => {
        if (cancelled || seq.current !== requestId) return
        setResult(null)
        setError({ key: postedKey, message: apiErrorText(err, 'Historical analytics failed') })
      })
    return () => { cancelled = true }
  }, [portfolio, start, end])

  if (!portfolio) {
    return (
      <div className="card wide historical-analytics">
        <p className="muted">Load a portfolio before requesting historical analytics from the frozen dataset.</p>
      </div>
    )
  }

  const units = result?.units || {}

  return (
    <div className="card wide historical-analytics">
      <div className="block-title">
        <h3>Historical analytics</h3>
        <BlockHelp id="historical-analytics" />
      </div>
      <p className="muted" role="note">
        Portfolio performance and risk over the selected historical window.
      </p>
      <details className="tech-details">
        <summary>How this page is calculated</summary>
        <p className="muted">
          Changing the range sends a new POST /api/v1/risk/historical-analytics.
          This terminal formats and charts API fields; it does not recompute
          returns, vol, Sharpe, beta, or drawdown. Benchmark is requested with
          include_benchmark true.
        </p>
      </details>
      <DataSourceBadge payload={current ? result : null} />
      <form className="ha-controls" onSubmit={(event) => event.preventDefault()}>
        <label>
          Start date
          <input
            type="date"
            value={start}
            onChange={(event) => setStart(event.target.value)}
          />
        </label>
        <label>
          End date
          <input
            type="date"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
          />
        </label>
        {waiting && <span className="muted">Requesting analytics…</span>}
      </form>
      {waiting && <div className="skel-strip" aria-hidden="true" />}
      {errorCurrent && <div className="error ha-error" role="alert">{error.message}</div>}
      {current && result && (
        <>
          <Identity result={result} />
          <SummaryTable result={result} />
          {result.notes?.length ? (
            <p className="muted ha-notes">{result.notes.join(' · ')}</p>
          ) : null}
          <div className="ha-block">
            <h3>Portfolio wealth</h3>
            <p className="muted">Wealth and cumulative return over the selected window.</p>
            <DatedSeriesChart
              series={result.wealth}
              unit={units.wealth}
              ariaLabel="Portfolio wealth"
              testId="ha-wealth-chart"
            />
            <DatedSeriesChart
              series={result.cumulative}
              unit={units.returns}
              ariaLabel="Cumulative return"
              testId="ha-cumulative-chart"
            />
          </div>
          <div className="ha-block">
            <h3>Drawdown</h3>
            <p className="muted">
              Peak-to-trough path over the window. Max drawdown {formatFraction(result.max_drawdown)}.
            </p>
            <details className="tech-details">
              <summary>Series unit</summary>
              <p className="muted">API drawdown series ({units.drawdown}). Values are ≤ 0.</p>
            </details>
            <DatedSeriesChart
              series={result.drawdown}
              unit={units.drawdown}
              ariaLabel="Drawdown"
              testId="ha-drawdown-chart"
              className="ha-drawdown"
            />
          </div>
          <div className="ha-block">
            <h3>Rolling volatility</h3>
            <p className="muted">Annualized rolling volatility over the selected window.</p>
            <DatedSeriesChart
              series={result.rolling_volatility}
              unit={units.volatility}
              ariaLabel="Rolling volatility"
              testId="ha-rolling-chart"
            />
          </div>
          <BenchmarkBlock benchmark={result.benchmark} />
          <div className="ha-block" data-testid="ha-var-es">
            <h3>VaR / ES</h3>
            <p className="muted">Historical VaR and Expected Shortfall as currency loss on the sliced window.</p>
            <table>
              <thead>
                <tr><th>Metric</th><th>Value</th><th>Unit</th></tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">95% VaR</th>
                  <td>{money(result.var_95)}</td>
                  <td>{units.var_es}</td>
                </tr>
                <tr>
                  <th scope="row">99% VaR</th>
                  <td>{money(result.var_99)}</td>
                  <td>{units.var_es}</td>
                </tr>
                <tr>
                  <th scope="row">99% ES</th>
                  <td>{money(result.expected_shortfall_99)}</td>
                  <td>{units.var_es}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <nav className="ha-links" data-testid="ha-links" aria-label="Related analytics">
            <a href={hashForPanel('var-es', 'contributors')}>Component VaR contributors</a>
            <a href={hashForPanel('risk-factors', 'kr-dv01')}>KR-DV01 tenor curve</a>
            <a href={hashForPanel('var-es', 'risk-change')}>Risk-change waterfall</a>
            <a href={hashForSection('risk-runs')}>Calculation provenance</a>
          </nav>
        </>
      )}
    </div>
  )
}
