import { api } from '../services/api'

const LEVEL_META = {
  critical: { color: 'var(--danger)',  icon: '🚨', cls: 'critical' },
  warning:  { color: 'var(--warning)', icon: '⚠️', cls: 'warning'  },
  info:     { color: 'var(--info)',    icon: 'ℹ️', cls: 'info'     },
}

export default function AlertPanel({ alerts, onResolve, onResolveAll }) {
  const handleResolve = async (id) => {
    try {
      await api.resolveAlert(id)
      onResolve?.(id)
    } catch (_) {}
  }

  const handleResolveAll = async () => {
    try {
      await api.resolveAllAlerts()
      onResolveAll?.()
    } catch (_) {}
  }

  const unresolved = alerts.filter(a => !a.resolved)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="section-label">
          Live Alerts — {unresolved.length} active
        </span>
        <button className="neu-btn neu-btn-sm" onClick={handleResolveAll}>
          ✔ Resolve All
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 420, overflowY: 'auto' }}>
        {alerts.length === 0 && (
          <div className="neu-inset text-center text-muted text-xs" style={{ padding: '24px 0' }}>
            No alerts recorded
          </div>
        )}

        {alerts.slice(0, 30).map(alert => {
          const meta = LEVEL_META[alert.level] || LEVEL_META.info
          return (
            <div
              key={alert.id}
              className={`alert-item ${meta.cls} ${alert.resolved ? 'resolved' : ''}`}
            >
              <span style={{ fontSize: 18, flexShrink: 0 }}>{meta.icon}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
                  {alert.title}
                </div>
                <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                  {alert.description}
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 4, alignItems: 'center' }}>
                  <span className={`neu-badge badge-${meta.cls === 'critical' ? 'danger' : meta.cls === 'warning' ? 'warning' : 'info'}`}>
                    {alert.level}
                  </span>
                  <span className="text-xs text-muted font-mono">{alert.source}</span>
                  {alert.resolved && (
                    <span style={{ fontSize: '0.65rem', color: 'var(--success)', fontWeight: 600 }}>✔ Resolved</span>
                  )}
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6, flexShrink: 0 }}>
                <span className="text-xs font-mono text-muted">{alert.timestamp}</span>
                {!alert.resolved && (
                  <button
                    className="neu-btn neu-btn-sm"
                    style={{ fontSize: '0.65rem', padding: '3px 10px' }}
                    onClick={() => handleResolve(alert.id)}
                  >
                    Resolve
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
