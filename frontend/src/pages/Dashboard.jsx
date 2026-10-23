import CameraFeed from '../components/CameraFeed'
import { GradeDonut, GradeBarChart } from '../components/Charts'
import { useNavigate } from 'react-router-dom'

/* ── Grade config ─────────────────────────────────────────── */
const GRADES = [
  { key: 'grade1', label: 'Grade 1 – Premium', color: 'var(--premium)',   fill: 'fill-premium',   bin: 1 },
  { key: 'grade2', label: 'Grade 2 – Good',    color: 'var(--grade1)',    fill: 'fill-grade1',    bin: 2 },
  { key: 'grade3', label: 'Grade 3 – Average', color: 'var(--grade2)',    fill: 'fill-grade2',    bin: 3 },
  { key: 'grade4', label: 'Grade 4 – Defect',  color: 'var(--defective)', fill: 'fill-defective', bin: 4 },
]

export default function Dashboard({ stats, lastBean, frame, calibrationReady }) {
  const navigate = useNavigate()
  const sc        = stats.sort_counts || {}
  const total     = stats.beans_processed || 0
  const isRunning = stats.status === 'running'

  return (
    <div className="page">

      {!calibrationReady && (
        <div className="neu-card" style={{ padding: '12px 16px', marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', border: '1px solid rgba(245,158,11,0.35)' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.78rem' }}>
            Calibrate one bean from each grade before starting sorting.
          </span>
          <button className="neu-btn neu-btn-sm" onClick={() => navigate('/calibration')} style={{ color: 'var(--warning)', fontWeight: 700 }}>
            Open calibration
          </button>
        </div>
      )}

      {/* ── Hero: camera left | grade distribution right ── */}
      <div className="dashboard-hero">

        {/* Live camera feed */}
        <div className="neu-card" style={{ padding: 16 }}>
          <div className="section-label" style={{ marginBottom: 12 }}>Live Camera Feed</div>
          <CameraFeed frame={frame} isRunning={isRunning} lastBean={lastBean} />
        </div>

        {/* Real-time grade distribution */}
        <div className="neu-card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="section-label">Real-Time Grade Distribution</div>

          {/* Donut */}
          <GradeDonut counts={sc} total={total} />

          {/* Grade rows with progress bars + bin badge */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {GRADES.map(g => {
              const count = sc[g.key] || 0
              const pct   = total > 0 ? (count / total) * 100 : 0
              return (
                <div key={g.key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', flex: 1, fontWeight: 500 }}>{g.label}</span>
                  <div style={{ width: 88 }}>
                    <div className="neu-progress-track" style={{ height: 6 }}>
                      <div className={`neu-progress-fill ${g.fill}`} style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                  <span className="font-mono" style={{ fontSize: '0.68rem', color: g.color, width: 32, textAlign: 'right', fontWeight: 700 }}>
                    {pct.toFixed(0)}%
                  </span>
                  <span className="font-mono" style={{ fontSize: '0.64rem', color: 'var(--text-muted)', width: 40, textAlign: 'right' }}>
                    {count.toLocaleString()}
                  </span>
                  <span style={{
                    fontSize: '0.58rem', fontWeight: 700,
                    background: 'var(--bg-deep)', color: g.color,
                    padding: '2px 7px', borderRadius: 'var(--r-full)',
                    boxShadow: 'var(--shadow-in)', flexShrink: 0,
                    minWidth: 38, textAlign: 'center',
                  }}>
                    Bin {g.bin}
                  </span>
                </div>
              )
            })}
          </div>

          {/* Bar chart */}
          <div style={{ marginTop: 2 }}>
            <div className="section-label" style={{ marginBottom: 6 }}>Count by Grade</div>
            <GradeBarChart counts={sc} />
          </div>
        </div>

      </div>
    </div>
  )
}
