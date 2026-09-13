import { useEffect, useRef, useState } from 'react'
import { historicalAnalytics } from '../api.js'
import BlockHelp from './BlockHelp'
import { DatedSeriesChart } from './RiskVisuals.jsx'
import { money } from '../lib/risk.mjs'

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
          <td>{result.sharpe == null ? 'undefined' : units.volatility}</td>
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
        Nested <code>benchmark</code> from the same result — {benchmark.instrument_id} / {benchmark.factor_column}.
        Relative analytics, not allocation advice.
      </p>
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
  const [error, setError] = useState('')
  const seq = useRef(0)

  useEffect(() => {
    if (!portfolio || !start || !end) return undefined
    const requestId = seq.current + 1
    seq.current = requestId
    let cancelled = false
    historicalAnalytics(buildRequest(portfolio, start, end))
      .then((next) => {
        if (cancelled || seq.current !== requestId) return
        setResult(next)
        setError('')
      })
      .catch((err) => {
        if (cancelled || seq.current !== requestId) return
        setResult(null)
        setError(apiErrorText(err, 'Historical analytics failed'))
      })
    return () => { cancelled = true }
  }, [portfolio, start, end])

  const waiting = Boolean(portfolio && start && end && !result && !error)

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
        One backend result powers this page. Changing the range sends a new
        POST /api/v1/risk/historical-analytics. This terminal formats and charts
        API fields; it does not recompute returns, vol, Sharpe, beta, or drawdown.
        Benchmark is requested with include_benchmark true.
      </p>
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
      {error && <div className="error ha-error" role="alert">{error}</div>}
      {result && (
        <>
          <Identity result={result} />
          <SummaryTable result={result} />
          {result.notes?.length ? (
            <p className="muted ha-notes">{result.notes.join(' · ')}</p>
          ) : null}
          <div className="ha-block">
            <h3>Cumulative / wealth</h3>
            <p className="muted">API <code>wealth</code> ({units.wealth}) and <code>cumulative</code> ({units.returns}).</p>
            <DatedSeriesChart
              series={result.wealth}
              ariaLabel="Portfolio wealth"
              testId="ha-wealth-chart"
            />
            <DatedSeriesChart
              series={result.cumulative}
              ariaLabel="Cumulative return"
              testId="ha-cumulative-chart"
            />
          </div>
          <div className="ha-block">
            <h3>Drawdown</h3>
            <p className="muted">
              API <code>drawdown</code> series and max_drawdown {formatFraction(result.max_drawdown)}
              {' '}({units.drawdown}). Values are ≤ 0.
            </p>
            <DatedSeriesChart
              series={result.drawdown}
              ariaLabel="Drawdown"
              testId="ha-drawdown-chart"
              className="ha-drawdown"
            />
          </div>
          <div className="ha-block">
            <h3>Rolling volatility</h3>
            <p className="muted">API <code>rolling_volatility</code> ({units.volatility}).</p>
            <DatedSeriesChart
              series={result.rolling_volatility}
              ariaLabel="Rolling volatility"
              testId="ha-rolling-chart"
            />
          </div>
          <BenchmarkBlock benchmark={result.benchmark} />
          <div className="ha-block" data-testid="ha-var-es">
            <h3>VaR / ES</h3>
            <p className="muted">Currency loss from HistoricalRiskEngine on the sliced window ({units.var_es}).</p>
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
            <a href="#var-es">Component VaR contributors</a>
            <a href="#var-es">Risk-change waterfall</a>
          </nav>
        </>
      )}
    </div>
  )
}
