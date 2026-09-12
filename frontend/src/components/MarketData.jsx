import { useState } from 'react'
import { searchInstruments } from '../api.js'

function capabilityLabel(row) {
  const badges = []
  if (row.supported_for_history) badges.push('History')
  if (row.supported_for_snapshot) badges.push('Snapshot')
  if (row.supported_for_risk_factor) badges.push('Risk factor')
  return badges.length ? badges.join(' · ') : 'Unsupported'
}

export default function MarketData() {
  const [query, setQuery] = useState('')
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)

  const onSearch = async (event) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    setStatus('')
    try {
      const hits = await searchInstruments(query)
      setRows(Array.isArray(hits) ? hits : [])
    } catch (err) {
      setRows([])
      setError(err?.body?.message || err.message || 'Search failed')
    } finally {
      setBusy(false)
    }
  }

  const onLoadHistory = (row) => {
    if (!row.supported_for_history) return
    setStatus('History load is not available yet')
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
        <button type="submit" disabled={busy}>Search</button>
      </form>
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
                    disabled={!row.supported_for_history}
                    onClick={() => onLoadHistory(row)}
                  >
                    Load History
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </div>
  )
}
