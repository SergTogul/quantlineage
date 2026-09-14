import { displayDataSource } from '../lib/dataSource.mjs'

/** Concise backend identity for analytics pages. Display only. */
export default function DataSourceBadge({ payload }) {
  const text = displayDataSource(payload)
  if (!text) return null
  return (
    <p className="data-source-badge" data-testid="data-source-badge">
      {text}
    </p>
  )
}
