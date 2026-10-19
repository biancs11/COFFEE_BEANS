import StatCard from '../components/StatCard'
import SortingBins from '../components/SortingBins'
import { ThroughputChart, GradeDonut } from '../components/Charts'

function fmtUptime(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  const p = n => String(n).padStart(2, '0')
  return `${p(h)}:${p(m)}:${p(sec)}`
}

export default function Overview({ stats, lastBean }) {
  const { sort_counts: sc, beans_processed, beans_per_minute, good_yield_pct, defect_rate_pct } = stats
  const total = beans_processed || 0

  return (
    <div className="page">

      {/* Hero */}
      <div className="neu-card mb-4" style={{ background: 'linear-gradient(135deg, #e8ecf1, #eef1f5)' }}>
        <div className="flex items-center justify-between gap-4" style={{ flexWrap: 'wrap' }}>
          <div>
            <h2 style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--coffee-dark)', marginBottom: 6 }}>
              Coffee Bean Sorting System
            </h2>
            <p className="text-sm text-muted" style={{ maxWidth: 500, lineHeight: 1.6 }}>
              Real-time grading via Raspberry Pi Camera + OpenCV. Classifies beans into
              <strong style={{ color: 'var(--premium)' }}> Premium</strong>,
              <strong style={{ color: 'var(--grade1)' }}> Grade 1</strong>,
              <strong style={{ color: 'var(--grade2)' }}> Grade 2</strong>,
              <strong style={{ color: 'var(--grade3)' }}> Grade 3</strong>, and
              <strong style={{ color: 'var(--defective)' }}> Defective</strong> with pneumatic ejection.
            </p>
            <div className="flex gap-2 mt-3" style={{ flexWrap: 'wrap' }}>
              {['📷 RPi Camera', '🤖 OpenCV AI', '💨 Pneumatic Ejection', '⚡ Real-time WS'].map(tag => (
                <span key={tag} className="neu-badge badge-muted" style={{ fontSize: '0.7rem' }}>{tag}</span>
              ))}
            </div>
          </div>
          <div className="flex gap-5" style={{ flexShrink: 0 }}>
            {[
              { label: 'Processed', val: total.toLocaleString(), color: 'var(--text-primary)' },
              { label: 'Yield',     val: `${good_yield_pct}%`,   color: 'var(--premium)'   },
              { label: 'Rate',      val: `${Math.round(beans_per_minute)}/min`, color: 'var(--grade1)' },
            ].map(s => (
              <div key={s.label} style={{ textAlign: 'center' }}>
                <div className="font-mono font-800" style={{ fontSize: '1.6rem', color: s.color }}>{s.val}</div>
                <div className="text-xs text-muted">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid-4 mb-4">
        <StatCard icon="📦" value={total.toLocaleString()} label="Total Processed" variant="coffee" delta="Live count" />
        <StatCard icon="✅" value={`${good_yield_pct}%`}   label="Good Yield"      variant="premium" delta="Target ≥96%" />
        <StatCard icon="⚡" value={`${Math.round(beans_per_minute)}`} label="Beans / min" variant="grade1" delta="0.5–2.0 kg/min" />
        <StatCard icon="❌" value={`${defect_rate_pct}%`}  label="Defect Rate"     variant="defective" delta="Target <5%" />
      </div>

      {/* Bins */}
      <div className="mb-4">
        <div className="section-label">Live Sorting Bins</div>
        <SortingBins counts={sc} lastBeanGrade={lastBean?.grade} />
      </div>

      {/* Charts */}
      <div className="grid-2 mb-4">
        <div className="neu-card">
          <div className="section-label mb-2">Quality & Throughput Trend</div>
          <ThroughputChart
            beansPerMinute={beans_per_minute}
            goodYield={good_yield_pct}
            defectRate={defect_rate_pct}
          />
        </div>
        <div className="neu-card">
          <div className="section-label mb-2">Grade Distribution</div>
          <GradeDonut counts={sc} total={total} />
        </div>
      </div>

      {/* System KPIs */}
      <div className="grid-3">
        {[
          { label: 'Session Uptime',      val: fmtUptime(stats.uptime_seconds), icon: '⏱️' },
          { label: 'Air Pressure',        val: `${stats.air_pressure_mpa} MPa`,  icon: '💨' },
          { label: 'Camera FPS',          val: `${stats.camera_fps} fps`,        icon: '📷' },
          { label: 'Conveyor Speed',      val: `${stats.conveyor_rpm} RPM`,       icon: '🔄' },
          { label: 'CPU Temperature',     val: `${stats.cpu_temp_c?.toFixed(1) ?? '—'}°C`, icon: '🌡️' },
          { label: 'Active Alerts',       val: stats.active_alerts,              icon: '🚨' },
        ].map(k => (
          <div key={k.label} className="neu-card-sm flex items-center gap-3">
            <span style={{ fontSize: 22 }}>{k.icon}</span>
            <div>
              <div className="font-mono font-bold" style={{ fontSize: '1rem', color: 'var(--text-primary)' }}>{k.val}</div>
              <div className="text-xs text-muted">{k.label}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
