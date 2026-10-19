import { useState, useEffect, useRef } from 'react'
import GradeCard from '../components/GradeCard'

const GRADE_GUIDE = [
  { grade: 'Premium',   color: 'var(--premium)',   cls: 'premium',   size: '≥ 8.0 mm', color_desc: 'Uniform deep brown, high saturation',  defects: 'None',         bin: 'Premium Bin'  },
  { grade: 'Grade 1',   color: 'var(--grade1)',    cls: 'grade_1',   size: '7.0–8.0mm', color_desc: 'Good brown, slight variation OK',       defects: 'Minor only',   bin: 'Grade 1 Bin'  },
  { grade: 'Grade 2',   color: 'var(--grade2)',    cls: 'grade_2',   size: '6.0–7.0mm', color_desc: 'Acceptable variation',                  defects: 'Surface OK',   bin: 'Grade 2 Bin'  },
  { grade: 'Grade 3',   color: 'var(--grade3)',    cls: 'grade_3',   size: '5.0–6.0mm', color_desc: 'Faded or uneven roast',                 defects: 'Sour/surface', bin: 'Grade 3 Bin'  },
  { grade: 'Defective', color: 'var(--defective)', cls: 'defective', size: '< 5.0 mm', color_desc: 'Black/burnt, pale/raw, mold, green',     defects: 'Severe',       bin: 'Defect Bin'   },
]

function GaugeRing({ value, color, size = 120 }) {
  const r    = 48
  const circ = 2 * Math.PI * r
  const dash = circ * (value / 100)

  return (
    <div className="gauge-wrap relative" style={{ width: size, height: size }}>
      <svg className="gauge-svg" width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle className="gauge-track" cx={size/2} cy={size/2} r={r} strokeWidth={10} />
        <circle
          className="gauge-fill"
          cx={size/2} cy={size/2} r={r}
          strokeWidth={10}
          stroke={color}
          strokeDasharray={`${dash} ${circ}`}
          style={{ filter: `drop-shadow(0 0 6px ${color})` }}
        />
      </svg>
      <div className="gauge-center">
        <div className="font-mono font-800" style={{ fontSize: '1.2rem', color: 'var(--text-primary)' }}>
          {Math.round(value)}%
        </div>
        <div className="text-xs text-muted">confidence</div>
      </div>
    </div>
  )
}

const GRADE_COLORS = {
  'Premium':   'var(--premium)',
  'Grade 1':   'var(--grade1)',
  'Grade 2':   'var(--grade2)',
  'Grade 3':   'var(--grade3)',
  'Defective': 'var(--defective)',
}

export default function Assessment({ lastBean, stats }) {
  const [history, setHistory] = useState([])

  useEffect(() => {
    if (!lastBean) return
    setHistory(prev => [lastBean, ...prev].slice(0, 12))
  }, [lastBean])

  const gradeColor = lastBean ? (GRADE_COLORS[lastBean.grade] || 'var(--text-muted)') : 'var(--text-muted)'
  const gradeCls   = lastBean ? lastBean.grade.toLowerCase().replace(' ', '_') : ''

  return (
    <div className="page">
      <div className="page-header">
        <h2>🤖 Feature 2 — AI-Powered Quality Assessment</h2>
        <p>
          OpenCV analyzes each bean's HSV color space, diameter, and surface texture to classify
          into Premium / Grade 1 / Grade 2 / Grade 3 / Defective with a real-time confidence score.
        </p>
      </div>

      <div className="grid-3 mb-4">

        {/* Confidence ring */}
        <div className="neu-card flex flex-col items-center gap-4" style={{ justifyContent: 'center', minHeight: 280 }}>
          <div className="section-label">AI Confidence</div>
          <GaugeRing value={lastBean?.confidence ?? 0} color={gradeColor} />
          {lastBean && (
            <span className={`grade-pill ${gradeCls}`} style={{ fontSize: '1rem', padding: '6px 20px' }}>
              {lastBean.grade}
            </span>
          )}
          {!lastBean && <span className="text-xs text-muted">Start system to begin</span>}
        </div>

        {/* Attribute analysis */}
        <div className="neu-card">
          <div className="section-label mb-3">Attribute Analysis</div>
          {lastBean ? (
            <>
              {/* Color swatch */}
              <div className="neu-inset flex items-center gap-3 mb-3">
                <div style={{
                  width: 36, height: 36, borderRadius: 8, flexShrink: 0,
                  background: `rgb(${lastBean.color_r},${lastBean.color_g},${lastBean.color_b})`,
                  boxShadow: 'var(--shadow-in)',
                }} />
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.8rem' }}>{lastBean.color_name}</div>
                  <div className="text-xs text-muted">{lastBean.roast_level}</div>
                </div>
              </div>

              {/* Attribute bars */}
              {[
                { icon: '🎨', label: 'Color Score',   val: `H:${lastBean.hue.toFixed(0)} S:${lastBean.saturation.toFixed(0)}`, pct: Math.min((lastBean.saturation / 255) * 100, 100), fill: 'fill-grade2' },
                { icon: '📏', label: 'Size Grade',    val: `${lastBean.size_mm} mm`,    pct: Math.min((lastBean.size_mm / 10) * 100, 100), fill: 'fill-grade1' },
                { icon: '💡', label: 'Brightness',    val: `${lastBean.brightness.toFixed(0)} / 255`, pct: (lastBean.brightness / 255) * 100, fill: 'fill-coffee' },
                { icon: '🔍', label: 'Quality Index', val: `${lastBean.confidence}%`,   pct: lastBean.confidence, fill: lastBean.confidence > 85 ? 'fill-success' : 'fill-grade2' },
              ].map(a => (
                <div key={a.label} className="attr-row">
                  <span className="attr-icon">{a.icon}</span>
                  <span className="attr-label">{a.label}</span>
                  <div className="attr-bar">
                    <div className="neu-progress-track" style={{ height: 6 }}>
                      <div className={`neu-progress-fill ${a.fill}`} style={{ width: `${a.pct}%` }} />
                    </div>
                  </div>
                  <span className="attr-value font-mono" style={{ fontSize: '0.68rem', width: 80, textAlign: 'right' }}>{a.val}</span>
                </div>
              ))}

              <div className="divider" />
              <div className="attr-row">
                <span className="attr-icon">🚫</span>
                <span className="attr-label">Defects</span>
                <span className="attr-value" style={{ color: lastBean.defects.length > 0 ? 'var(--danger)' : 'var(--success)', fontSize: '0.72rem' }}>
                  {lastBean.defects.length > 0 ? lastBean.defects.join(' • ') : 'Clean'}
                </span>
              </div>
            </>
          ) : (
            <p className="text-xs text-muted text-center" style={{ padding: '24px 0' }}>Waiting for detection…</p>
          )}
        </div>

        {/* Recent history */}
        <div className="neu-card">
          <div className="section-label mb-3">Assessment History</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 320, overflowY: 'auto' }}>
            {history.length === 0 && (
              <p className="text-xs text-muted text-center" style={{ padding: '20px 0' }}>No history yet</p>
            )}
            {history.map((b, i) => {
              const c = GRADE_COLORS[b.grade] || 'var(--text-muted)'
              return (
                <div key={i} className="neu-inset flex items-center gap-3">
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: c, flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 600, color: c }}>{b.grade}</div>
                    <div className="text-xs text-muted">{b.size_mm}mm · {b.color_name}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div className="font-mono text-xs" style={{ color: c }}>{b.confidence}%</div>
                    <div className="text-xs text-muted">{b.timestamp}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Grade reference table */}
      <div className="neu-card">
        <div className="section-label mb-3">Grade Classification Reference</div>
        <div style={{ overflowX: 'auto' }}>
          <table className="neu-table">
            <thead>
              <tr>
                <th>Grade</th><th>Size Range</th><th>Color Profile</th>
                <th>Defect Tolerance</th><th>Target Bin</th>
              </tr>
            </thead>
            <tbody>
              {GRADE_GUIDE.map(g => (
                <tr key={g.grade}>
                  <td>
                    <span className={`grade-pill ${g.cls}`}>{g.grade}</span>
                  </td>
                  <td className="td-mono">{g.size}</td>
                  <td className="text-sm">{g.color_desc}</td>
                  <td>
                    <span className={`neu-badge ${g.grade === 'Defective' ? 'badge-danger' : g.grade === 'Grade 3' ? 'badge-warning' : 'badge-success'}`}>
                      {g.defects}
                    </span>
                  </td>
                  <td className="text-sm">{g.bin}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
