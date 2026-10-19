export default function StatCard({ icon, value, label, variant = 'coffee', delta }) {
  return (
    <div className={`stat-card ${variant}`}>
      <div className={`stat-icon ${variant}`}>{icon}</div>
      <div className="stat-info">
        <div className="stat-value">{value}</div>
        <div className="stat-label">{label}</div>
        {delta && (
          <div className="text-xs" style={{ marginTop: 3, color: 'var(--text-muted)' }}>{delta}</div>
        )}
      </div>
    </div>
  )
}
