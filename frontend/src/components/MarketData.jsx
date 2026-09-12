import { useState } from 'react'
import {
  buildPublicSnapshot,
  freezePublicDataset,
  getInstrumentHistory,
  getInstrumentQuality,
  searchInstruments,
} from '../api.js'

function capabilityLabel(row) {
  const badges = []
  if (row.supported_for_history) badges.push('History')
  if (row.supported_for_snapshot) badges.push('Snapshot')
  if (row.supported_for_risk_factor) badges.push('Risk factor')
  return badges.length ? badges.join(' · ') : 'Unsupported'
}

function coverageText(quality) {
  if (!quality?.first_observation || !quality?.last_observation) return 'n/a'
  return `${quality.first_observation} – ${quality.last_observation} (${quality.observation_count})`
}

function apiErrorText(err, fallback) {
  const code = err?.body?.code
  const message = err?.body?.message || err?.message || fallback
  return code ? `${code}: ${message}` : message
}

export default function MarketData() {
  const [query, setQuery] = useState('')
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [asOf, setAsOf] = useState('')
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [quality, setQuality] = useState(null)
  const [history, setHistory] = useState(null)
  const [dataset, setDataset] = useState(null)
  const [snapshot, setSnapshot] = useState(null)
  const [busy, setBusy] = useState(false)

  const onSearch = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    setStatus('')
    setQuality(null)
    setHistory(null)
    try {
      const hits = await searchInstruments(query)
      setRows(Array.isArray(hits) ? hits : [])
    } catch (err) {
      setRows([])
      setError(apiErrorText(err, 'Search failed'))
    } finally {
      setBusy(false)
    }
  }

  const onLoadHistory = async (row) => {
    if (!row.supported_for_history) return
    setBusy(true)
    setError('')
    setStatus('')
    setHistory(null)
    try {
      const result = await getInstrumentHistory(row.instrument_id, start, end)
      setHistory(result)
    } catch (err) {
      setError(apiErrorText(err, 'History load failed'))
    } finally {
      setBusy(false)
    }
  }

  const onInspectQuality = async (row) => {
    if (!row.supported_for_history) return
    setBusy(true)
    setError('')
    setStatus('')
    setQuality(null)
    try {
      const result = await getInstrumentQuality(row.instrument_id, start, end)
      setQuality(result)
    } catch (err) {
      setError(apiErrorText(err, 'Quality inspect failed'))
    } finally {
      setBusy(false)
    }
  }

  const onFreeze = async () => {
    setBusy(true)
    setError('')
    setStatus('')
    setDataset(null)
    try {
      const result = await freezePublicDataset(start, end)
      setDataset(result)
    } catch (err) {
      setError(apiErrorText(err, 'Freeze dataset failed'))
    } finally {
      setBusy(false)
    }
  }

  const onBuildSnapshot = async () => {
    setBusy(true)
    setError('')
    setStatus('')
    setSnapshot(null)
    try {
      const result = await buildPublicSnapshot(asOf)
      setSnapshot(result)
    } catch (err) {
      setError(apiErrorText(err, 'Build snapshot failed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card wide market-data">
      <form className="query market-data-search" onSubmit={onSearch}>
        <label>
          Instrument search
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Apple, AAPL, DGS10…"
            autoComplete="off"
          />
        </label>
        <label>
          Start date
          <input
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </label>
        <label>
          End date
          <input
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </label>
        <button type="submit" disabled={busy}>Search</button>
      </form>
      <div className="market-data-actions">
        <label>
          As of
          <input
            type="date"
            value={asOf}
            onChange={(e) => setAsOf(e.target.value)}
          />
        </label>
        <button type="button" disabled={busy || !start || !end} onClick={onFreeze}>
          Freeze dataset
        </button>
        <button type="button" disabled={busy || !asOf} onClick={onBuildSnapshot}>
          Build snapshot
        </button>
      </div>
      {error ? <div className="error" role="alert">{error}</div> : null}
      {status ? <p className="muted">{status}</p> : null}
      {rows.length === 0 && !error && !busy ? (
        <p className="muted">No instruments yet. Search the curated catalog.</p>
      ) : null}
      {rows.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>Id</th>
              <th>Name</th>
              <th>Source</th>
              <th>Symbol</th>
              <th>Type</th>
              <th>Currency</th>
              <th>Capabilities</th>
              <th>History</th>
              <th>Quality</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.instrument_id}>
                <td>{row.instrument_id}</td>
                <td>{row.display_name}</td>
                <td>{row.provider}</td>
                <td>{row.source_symbol}</td>
                <td>{row.asset_type}</td>
                <td>{row.currency}</td>
                <td>{capabilityLabel(row)}</td>
                <td>
                  <button
                    type="button"
                    disabled={!row.supported_for_history || busy}
                    onClick={() => onLoadHistory(row)}
                  >
                    Load History
                  </button>
                </td>
                <td>
                  <button
                    type="button"
                    disabled={!row.supported_for_history || busy}
                    onClick={() => onInspectQuality(row)}
                  >
                    Inspect quality
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {history?.points?.length ? (
        <section aria-label="Series history">
          <table aria-label="History">
            <thead>
              <tr>
                <th>Date</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {history.points.map((point) => (
                <tr key={point.observation_date}>
                  <td>{point.observation_date}</td>
                  <td>{point.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
      {quality ? (
        <section aria-label="Series quality">
          <dl>
            <div>
              <dt>Source</dt>
              <dd>{quality.source}</dd>
            </div>
            <div>
              <dt>Coverage</dt>
              <dd>{coverageText(quality)}</dd>
            </div>
            <div>
              <dt>Last observation</dt>
              <dd>{quality.last_observation}</dd>
            </div>
            <div>
              <dt>Stale</dt>
              <dd>{quality.stale ? 'stale' : 'fresh'}</dd>
            </div>
            <div>
              <dt>Missing</dt>
              <dd>{quality.missing_count}</dd>
            </div>
            <div>
              <dt>Content hash</dt>
              <dd>{quality.content_hash}</dd>
            </div>
            <div>
              <dt>Normalization version</dt>
              <dd>{quality.normalization_version}</dd>
            </div>
          </dl>
        </section>
      ) : null}
      {dataset ? (
        <section aria-label="Frozen dataset">
          <dl>
            <div>
              <dt>Dataset id</dt>
              <dd>{dataset.dataset_id}</dd>
            </div>
            <div>
              <dt>Dataset version</dt>
              <dd>{dataset.dataset_version}</dd>
            </div>
            {dataset.csv_path ? (
              <div>
                <dt>CSV</dt>
                <dd>{dataset.csv_path}</dd>
              </div>
            ) : null}
          </dl>
        </section>
      ) : null}
      {snapshot ? (
        <section aria-label="Public snapshot">
          <dl>
            <div>
              <dt>Snapshot id</dt>
              <dd>{snapshot.id}</dd>
            </div>
            <div>
              <dt>As of</dt>
              <dd>{snapshot.as_of}</dd>
            </div>
            <div>
              <dt>Content hash</dt>
              <dd>{snapshot.content_hash}</dd>
            </div>
          </dl>
        </section>
      ) : null}
    </div>
  )
}
