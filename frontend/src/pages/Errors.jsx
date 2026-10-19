import AlertPanel from '../components/AlertPanel'
import StatCard from '../components/StatCard'

export default function Errors({ alerts, stats, onResolve, onResolveAll }) {
  const criticals = alerts.filter(a => a.level === 'critical' && !a.resolved).length
  const warnings  = alerts.filter(a => a.level === 'warning'  && !a.resolved).length
  const total     = alerts.length

  const fmtUptime = (s) => {
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
    const p = n => String(n).padStart(2, '0')
    return `${p(h)}:${p(m)}:${p(sec)}`
  }

  return (
    <div className="page">
      <div className="page-header">
        <h2>🚨 Feature 4 — Sorting Error Monitoring</h2>
        <p>
          Continuously monitors sorting operations for incorrect sorts, missed detections,
          and hardware anomalies. Real-time alerts with three severity levels.
        </p>
      </div>

      <div className="grid-4 mb-4">
        <StatCard icon="🚨" value={criticals}  label="Active Criticals" variant="defective" />
        <StatCard icon="⚠️" value={warnings}   label="Active Warnings"  variant="grade2"    />
        <StatCard icon="📋" value={total}       label="Total Events"     variant="info"      />
        <StatCard icon="📊" value={`${stats.defect_rate_pct}%`} label="Defect Rate" variant="grade3" />
      </div>

      <div className="grid-2 mb-4">
        {/* Alert feed */}
        <div className="neu-card" style={{ gridColumn: 'span 1' }}>
          <AlertPanel alerts={alerts} onResolve={onResolve} onResolveAll={onResolveAll} />
        </div>

        {/* Safety + cycle summary */}
        <div className="flex flex-col gap-3">

          <div className="neu-card">
            <div className="section-label mb-3">Safety Features</div>
            {[
              { label: 'Emergency Stop',       status: 'Armed',   ok: true  },
              { label: 'Overcurrent Protect.',  status: 'Active',  ok: true  },
              { label: 'Air Pressure Monitor',  status: 'Online',  ok: true  },
              { label: 'Jam Detection',         status: 'Online',  ok: true  },
              { label: 'Overheat Shutdown',     status: stats.cpu_temp_c > 80 ? 'TRIGGERED' : 'Standby', ok: stats.cpu_temp_c <= 80 },
            ].map(s => (
              <div key={s.label} className="attr-row">
                <span className="attr-icon">{s.ok ? '✅' : '🚨'}</span>
                <span className="attr-label">{s.label}</span>
                <span className={`neu-badge ${s.ok ? 'badge-success' : 'badge-danger'}`}>{s.status}</span>
              </div>
            ))}
          </div>

          <div className="neu-card">
            <div className="section-label mb-3">Session Cycle Summary</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {[
                { val: stats.beans_processed,                 label: 'Processed',      color: 'var(--text-primary)' },
                { val: stats.sort_counts?.defective || 0,     label: 'Defects Found',  color: 'var(--defective)'    },
                { val: stats.active_alerts,                   label: 'Active Alerts',  color: 'var(--warning)'      },
                { val: fmtUptime(stats.uptime_seconds),       label: 'Session Uptime', color: 'var(--grade1)'       },
                { val: `${stats.air_pressure_mpa} MPa`,       label: 'Air Pressure',   color: 'var(--text-primary)' },
                { val: `${stats.cpu_temp_c?.toFixed(1) ?? '—'}°C`, label: 'CPU Temp', color: stats.cpu_temp_c > 70 ? 'var(--warning)' : 'var(--text-primary)' },
              ].map(k => (
                <div key={k.label} className="neu-inset text-center">
                  <div className="font-mono font-800" style={{ fontSize: '1.1rem', color: k.color }}>{k.val}</div>
                  <div className="text-xs text-muted">{k.label}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="neu-card">
            <div className="section-label mb-3">Valve Fire Count</div>
            {Object.entries(stats.valve_fires || {}).map(([bin, count]) => (
              <div key={bin} className="attr-row">
                <span className="attr-icon">💨</span>
                <span className="attr-label">{bin} valve</span>
                <span className="attr-value font-mono">{count} fires</span>
              </div>
            ))}
            {!stats.valve_fires || Object.keys(stats.valve_fires).length === 0 && (
              <span className="text-xs text-muted">No valve activity</span>
            )}
          </div>

        </div>
      </div>
    </div>
  )
}
