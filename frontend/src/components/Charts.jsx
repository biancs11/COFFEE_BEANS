import { useState, useEffect, useRef } from 'react'
import {
  LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'

/* ── Shared tooltip style — reads CSS vars so it works in both themes ── */
function tooltipStyle() {
  const bg = getComputedStyle(document.documentElement)
    .getPropertyValue('--tooltip-bg').trim() || '#e8ecf1'
  const text = getComputedStyle(document.documentElement)
    .getPropertyValue('--text-primary').trim() || '#2d3748'
  return {
    background: bg,
    border: 'none',
    borderRadius: 12,
    boxShadow: 'var(--shadow-out)',
    fontSize: 11,
    color: text,
  }
}

/* ── Rolling throughput / yield / defect line chart ───────── */
export function ThroughputChart({ beansPerMinute, goodYield, defectRate }) {
  const [data, setData] = useState(() =>
    Array.from({ length: 30 }, (_, i) => ({ t: i, bpm: 0, yield: 0, defect: 0 }))
  )
  const counterRef = useRef(30)

  useEffect(() => {
    setData(prev => {
      const next = [...prev.slice(1), {
        t:      counterRef.current++,
        bpm:    Math.round(beansPerMinute),
        yield:  Math.round(goodYield),
        defect: Math.round(defectRate),
      }]
      return next
    })
  }, [beansPerMinute, goodYield, defectRate])

  return (
    <ResponsiveContainer width="100%" height={175}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
        <XAxis dataKey="t" hide />
        <YAxis tick={{ fontSize: 10, fill: 'var(--chart-axis)' }} />
        <Tooltip contentStyle={tooltipStyle()} />
        <Legend wrapperStyle={{ fontSize: 11, color: 'var(--text-muted)' }} />
        <Line type="monotone" dataKey="yield"  stroke="var(--premium)"   strokeWidth={2}   dot={false} name="Good Yield %" />
        <Line type="monotone" dataKey="defect" stroke="var(--defective)" strokeWidth={1.5} dot={false} strokeDasharray="4 3" name="Defect %" />
        <Line type="monotone" dataKey="bpm"    stroke="var(--grade1)"    strokeWidth={1.5} dot={false} name="Beans/min" />
      </LineChart>
    </ResponsiveContainer>
  )
}

/* ── Grade distribution donut ──────────────────────────────── */
const GRADE_COLORS_HEX = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444']

export function GradeDonut({ counts, total }) {
  const data = [
    { name: 'Grade 1 – Premium', value: counts.grade1 || 0 },
    { name: 'Grade 2 – Good',    value: counts.grade2 || 0 },
    { name: 'Grade 3 – Average', value: counts.grade3 || 0 },
    { name: 'Grade 4 – Defect',  value: counts.grade4 || 0 },
  ].filter(d => d.value > 0)

  const goodPct = total > 0
    ? Math.round(((total - (counts.grade4 || 0)) / total) * 100)
    : 0

  return (
    <div style={{ position: 'relative', width: '100%' }}>
      <ResponsiveContainer width="100%" height={180}>
        <PieChart>
          <Pie
            data={data.length > 0 ? data : [{ name: 'No data', value: 1 }]}
            cx="50%" cy="50%"
            innerRadius={52} outerRadius={78}
            paddingAngle={2}
            dataKey="value"
            stroke="none"
          >
            {(data.length > 0 ? data : [{ name: 'No data' }]).map((_, i) => (
              <Cell key={i} fill={data.length > 0 ? GRADE_COLORS_HEX[i % GRADE_COLORS_HEX.length] : '#c8cdd4'} />
            ))}
          </Pie>
          <Tooltip contentStyle={tooltipStyle()} />
        </PieChart>
      </ResponsiveContainer>

      {/* Centre label */}
      <div style={{
        position: 'absolute', top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        textAlign: 'center', pointerEvents: 'none',
      }}>
        <div className="font-mono font-800" style={{ fontSize: '1.35rem', color: 'var(--text-primary)', lineHeight: 1 }}>
          {goodPct}%
        </div>
        <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: 2 }}>Good Yield</div>
      </div>
    </div>
  )
}

/* ── Grade horizontal bar chart ───────────────────────────── */
const GRADE_ROWS = [
  { key: 'grade1', label: 'Grade 1 – Premium', color: '#10b981', bg: 'rgba(16,185,129,0.18)'  },
  { key: 'grade2', label: 'Grade 2 – Good',    color: '#3b82f6', bg: 'rgba(59,130,246,0.18)'  },
  { key: 'grade3', label: 'Grade 3 – Average', color: '#f59e0b', bg: 'rgba(245,158,11,0.18)'  },
  { key: 'grade4', label: 'Grade 4 – Defect',  color: '#ef4444', bg: 'rgba(239,68,68,0.18)'   },
]

export function GradeBarChart({ counts }) {
  const max = Math.max(1, ...GRADE_ROWS.map(g => counts[g.key] || 0))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
      {GRADE_ROWS.map(g => {
        const count = counts[g.key] || 0
        const pct   = (count / max) * 100

        return (
          <div key={g.key} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>

            {/* Label */}
            <span style={{
              fontSize: '0.68rem', fontWeight: 600,
              color: 'var(--text-secondary)',
              width: 62, flexShrink: 0,
            }}>
              {g.label}
            </span>

            {/* Track + fill */}
            <div style={{
              flex: 1, height: 22,
              background: 'var(--bg-deep)',
              borderRadius: 6,
              boxShadow: 'var(--shadow-in)',
              overflow: 'hidden',
              position: 'relative',
            }}>
              <div style={{
                position: 'absolute', inset: 0,
                width: `${pct}%`,
                background: `linear-gradient(90deg, ${g.color}cc, ${g.color})`,
                borderRadius: 6,
                transition: 'width 0.6s ease',
                boxShadow: `0 0 10px ${g.color}55`,
              }} />
              {/* subtle inner glow on track */}
              <div style={{
                position: 'absolute', inset: 0,
                background: `linear-gradient(90deg, transparent 0%, ${g.bg} 100%)`,
                borderRadius: 6,
                pointerEvents: 'none',
              }} />
            </div>

            {/* Count */}
            <span className="font-mono" style={{
              fontSize: '0.68rem', fontWeight: 700,
              color: g.color,
              width: 36, textAlign: 'right', flexShrink: 0,
            }}>
              {count.toLocaleString()}
            </span>
          </div>
        )
      })}
    </div>
  )
}
