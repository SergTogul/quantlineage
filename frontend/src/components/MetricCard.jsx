export default function MetricCard({label, value}) {
  return <div className="card metric"><div className="muted">{label}</div><strong>{value}</strong></div>
}
