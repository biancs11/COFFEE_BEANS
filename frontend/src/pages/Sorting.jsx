import SortingBins from '../components/SortingBins'
import { GradeBarChart } from '../components/Charts'
import { api } from '../services/api'

const GRADE_MAP = {
  Premium:   { color: 'var(--premium)',   icon: '⭐', next: 'Premium Bin' },
  'Grade 1': { color: 'var(--grade1)',    icon: '🔵', next: 'Grade 1 Bin' },
  'Grade 2': { color: 'var(--grade2)',    icon: '🟡', next: 'Grade 2 Bin' },
  'Grade 3': { color: 'var(--grade3)',    icon: '🟣', next: 'Grade 3 Bin' },
  Defective: { color: 'var(--defective)', icon: '❌', next: 'Defect Bin — Ejected' },
}

export default function Sorting({ stats, lastBean, onToast }) {
  const { sort_counts: sc } = stats
  const total   = stats.beans_processed || 0
  const defPct  = total > 0 ? ((sc.defective / total) * 100).toFixed(1) : '0.0'
  const goodPct = total > 0 ? (((total - sc.defective) / total) * 100).toFixed(1) : '0.0'

  const meta = lastBean ? (GRADE_MAP[lastBean.grade] || GRADE_MAP['Grade 3']) : null

  const handleEject = async () => {
    try {
      await api.sendCommand('start')   // just a ping; actual eject is auto
      onToast?.('Manual eject command sent', 'info')
    } catch (e) {
      onToast?.(`Error: ${e.message}`, 'danger')
    }
  }

  return (
    <div className="page">
      <div className="page-header">
        <h2>📦 Feature 3 — Automated Sorting & Recommendation</h2>
        <p>
          Pneumatic solenoid valves (24V DC) fire precise 20–50ms air bursts at 0.4–0.8 MPa to
          divert defective beans. Grade screens (8/7/6/5mm) separate remaining beans by size into
          designated collection bins.
        </p>
      </div>

      {/* Last bean recommendation */}
      <div className="neu-card mb-4">
        <div className="flex items-center gap-4" style={{ flexWrap: 'wrap' }}>
          <div>
            <div className="section-label mb-1">Current Recommendation</div>
            {meta ? (
              <div className="flex items-center gap-3">
                <span style={{ fontSize: 28 }}>{meta.icon}</span>
                <div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: meta.color }}>{lastBean.grade}</div>
                  <div className="text-sm text-muted">→ {meta.next}</div>
                </div>
                <div style={{ marginLeft: 16 }}>
                  <div className="font-mono text-xs text-muted">Confidence</div>
                  <div className="font-mono font-bold" style={{ color: meta.color, fontSize: '1.2rem' }}>
                    {lastBean.confidence}%
                  </div>
                </div>
                <div style={{ marginLeft: 8 }}>
                  <div className="font-mono text-xs text-muted">Size</div>
                  <div className="font-mono font-bold" style={{ fontSize: '1.2rem' }}>
                    {lastBean.size_mm} mm
                  </div>
                </div>
              </div>
            ) : (
              <span className="text-xs text-muted">No bean detected yet</span>
            )}
          </div>
          <div style={{ flex: 1 }} />
          <div className="flex gap-3">
            <div className="neu-inset text-center" style={{ minWidth: 80 }}>
              <div className="font-mono font-800 text-success" style={{ fontSize: '1.4rem' }}>{goodPct}%</div>
              <div className="text-xs text-muted">Good Yield</div>
            </div>
            <div className="neu-inset text-center" style={{ minWidth: 80 }}>
              <div className="font-mono font-800 text-danger" style={{ fontSize: '1.4rem' }}>{defPct}%</div>
              <div className="text-xs text-muted">Defect Rate</div>
            </div>
            <div className="neu-inset text-center" style={{ minWidth: 80 }}>
              <div className="font-mono font-800" style={{ fontSize: '1.4rem' }}>{sc.defective}</div>
              <div className="text-xs text-muted">Ejected</div>
            </div>
          </div>
        </div>
      </div>

      {/* Bins */}
      <div className="mb-4">
        <div className="section-label mb-3">Live Sorting Bins</div>
        <SortingBins counts={sc} lastBeanGrade={lastBean?.grade} />
      </div>

      <div className="grid-2 mb-4">
        {/* Bar chart */}
        <div className="neu-card">
          <div className="section-label mb-3">Grade Distribution (Count)</div>
          <GradeBarChart counts={sc} />
        </div>

        {/* Ejection system status */}
        <div className="neu-card">
          <div className="section-label mb-3">Ejection System Status</div>

          {[
            { label: 'Good Yield',       val: `${goodPct}%`,  fill: 'fill-success', pct: parseFloat(goodPct)  },
            { label: 'Defect Rate',      val: `${defPct}%`,   fill: 'fill-defective', pct: parseFloat(defPct) },
          ].map(r => (
            <div key={r.label} className="mb-3">
              <div className="flex justify-between text-xs text-muted mb-1">
                <span>{r.label}</span>
                <span className="font-mono font-bold" style={{ color: r.fill.includes('success') ? 'var(--success)' : 'var(--danger)' }}>{r.val}</span>
              </div>
              <div className="neu-progress-track">
                <div className={`neu-progress-fill ${r.fill}`} style={{ width: `${r.pct}%` }} />
              </div>
            </div>
          ))}

          <div className="divider" />
          <div className="section-label mb-2">Hardware Specs</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {[
              ['Pressure',   `${stats.air_pressure_mpa} MPa`],
              ['Valve',      '2/2-way NC, 24V'],
              ['Response',   '5–10 ms'],
              ['Air Pulse',  '20–50 ms'],
              ['Nozzle Dia', '1–2 mm'],
              ['Compressor', '50–100 L/min'],
            ].map(([k, v]) => (
              <div key={k} className="neu-inset">
                <div className="text-xs text-muted">{k}</div>
                <div className="font-mono" style={{ fontSize: '0.75rem', fontWeight: 600 }}>{v}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Sort table */}
      <div className="neu-card">
        <div className="section-label mb-3">Sort Count Summary</div>
        <table className="neu-table">
          <thead>
            <tr><th>Grade</th><th>Count</th><th>Distribution</th><th>% Share</th><th>Bin</th></tr>
          </thead>
          <tbody>
            {[
              { key: 'premium',   grade: 'Premium',   fill: 'fill-premium',   color: 'var(--premium)',   bin: 'Premium Bin'  },
              { key: 'grade1',    grade: 'Grade 1',   fill: 'fill-grade1',    color: 'var(--grade1)',    bin: 'Grade 1 Bin'  },
              { key: 'grade2',    grade: 'Grade 2',   fill: 'fill-grade2',    color: 'var(--grade2)',    bin: 'Grade 2 Bin'  },
              { key: 'grade3',    grade: 'Grade 3',   fill: 'fill-grade3',    color: 'var(--grade3)',    bin: 'Grade 3 Bin'  },
              { key: 'defective', grade: 'Defective', fill: 'fill-defective', color: 'var(--defective)', bin: 'Defect Bin'   },
            ].map(r => {
              const count = sc[r.key] || 0
              const pct   = total > 0 ? ((count / total) * 100).toFixed(1) : '0.0'
              return (
                <tr key={r.key}>
                  <td>
                    <span className={`grade-pill ${r.key === 'grade1' ? 'grade_1' : r.key === 'grade2' ? 'grade_2' : r.key === 'grade3' ? 'grade_3' : r.key}`}>
                      {r.grade}
                    </span>
                  </td>
                  <td className="td-mono font-bold">{count}</td>
                  <td style={{ width: '30%' }}>
                    <div className="neu-progress-track" style={{ height: 7 }}>
                      <div className={`neu-progress-fill ${r.fill}`} style={{ width: `${pct}%` }} />
                    </div>
                  </td>
                  <td className="td-mono" style={{ color: r.color }}>{pct}%</td>
                  <td className="text-sm text-muted">{r.bin}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
