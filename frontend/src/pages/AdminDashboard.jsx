import { useState, useEffect, useRef, useCallback } from 'react'
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Legend,
  BarChart, Bar,
} from 'recharts'
import { api } from '../services/api'

/* ── Grade colour map ─────────────────────────────────────── */
const GRADE_CFG = [
  { key: 'grade1', label: 'Grade 1 – Premium', color: '#10b981', hex: '#10b981' },
  { key: 'grade2', label: 'Grade 2 – Good',    color: '#3b82f6', hex: '#3b82f6' },
  { key: 'grade3', label: 'Grade 3 – Average', color: '#f59e0b', hex: '#f59e0b' },
  { key: 'grade4', label: 'Grade 4 – Defect',  color: '#ef4444', hex: '#ef4444' },
]

/* ── Tooltip style ────────────────────────────────────────── */
function tooltipStyle() {
  const bg   = getComputedStyle(document.documentElement).getPropertyValue('--tooltip-bg').trim() || '#1e2130'
  const text = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim() || '#e2e8f0'
  return { background: bg, border: 'none', borderRadius: 10, fontSize: 11, color: text, boxShadow: '0 4px 20px rgba(0,0,0,0.3)' }
}

/* ── Stat card ────────────────────────────────────────────── */
function AdminStat({ label, value, sub, color = 'var(--text-primary)', icon }) {
  return (
    <div className="admin-stat-card">
      <div className="admin-stat-icon" style={{ background: color + '18' }}>
        <span style={{ fontSize: 18 }}>{icon}</span>
      </div>
      <div style={{ flex: 1 }}>
        <div className="admin-stat-value" style={{ color }}>{value}</div>
        <div className="admin-stat-label">{label}</div>
        {sub && <div className="admin-stat-sub">{sub}</div>}
      </div>
    </div>
  )
}

/* ── Section header ───────────────────────────────────────── */
function SectionHeader({ title, icon, badge }) {
  return (
    <div className="admin-section-header">
      <span style={{ fontSize: 16 }}>{icon}</span>
      <span className="admin-section-title">{title}</span>
      {badge && <span className="admin-section-badge">{badge}</span>}
    </div>
  )
}

/* ══════════════════════════════════════════════════════════
   MAIN ADMIN DASHBOARD
══════════════════════════════════════════════════════════ */
export default function AdminDashboard({ stats, lastBean }) {
  const sc    = stats.sort_counts || {}
  const total = stats.beans_processed || 0

  /* ── Rolling trend data (last 40 ticks) ── */
  const [trend, setTrend]         = useState(() =>
    Array.from({ length: 40 }, (_, i) => ({
      t: i, g1: 0, g2: 0, g3: 0, g4: 0,
      defectRate: 0, confidence: 0, bpm: 0,
    }))
  )
  const tickRef = useRef(40)

  useEffect(() => {
    setTrend(prev => {
      const defectRate  = total > 0 ? ((sc.grade4 || 0) / total * 100) : 0
      const goodYield   = total > 0 ? (((total - (sc.grade4 || 0)) / total) * 100) : 0
      return [...prev.slice(1), {
        t:          tickRef.current++,
        g1:         sc.grade1 || 0,
        g2:         sc.grade2 || 0,
        g3:         sc.grade3 || 0,
        g4:         sc.grade4 || 0,
        defectRate: parseFloat(defectRate.toFixed(1)),
        goodYield:  parseFloat(goodYield.toFixed(1)),
        bpm:        Math.round(stats.beans_per_minute || 0),
        confidence: lastBean ? parseFloat((lastBean.confidence || 0).toFixed(1)) : 0,
      }]
    })
  }, [stats.beans_processed, stats.beans_per_minute, lastBean?.confidence])

  /* ── Bean history log (last 80 beans) ── */
  const [beanLog, setBeanLog] = useState([])
  useEffect(() => {
    if (!lastBean) return
    setBeanLog(prev => [
      { ...lastBean, ts: new Date().toLocaleTimeString() },
      ...prev,
    ].slice(0, 80))
  }, [lastBean])

  /* ── Session summary from API ── */
  const [sessions, setSessions] = useState([])
  const fetchSessions = useCallback(async () => {
    try {
      const data = await api.getSessions(10)
      setSessions(data || [])
    } catch (_) {}
  }, [])
  useEffect(() => { fetchSessions() }, [fetchSessions])
  useEffect(() => {
    const id = setInterval(fetchSessions, 15000)
    return () => clearInterval(id)
  }, [fetchSessions])

  /* ── Computed values ── */
  const defectRate  = total > 0 ? ((sc.grade4 || 0) / total * 100) : 0
  const goodYield   = total > 0 ? (((total - (sc.grade4 || 0)) / total) * 100) : 0
  const avgConf     = beanLog.length > 0
    ? (beanLog.slice(0, 20).reduce((a, b) => a + (b.confidence || 0), 0) / Math.min(beanLog.length, 20))
    : 0

  /* ── Pie data ── */
  const pieData = GRADE_CFG
    .map(g => ({ name: g.label, value: sc[g.key] || 0, color: g.color }))
    .filter(d => d.value > 0)

  /* ── Size distribution buckets from bean log ── */
  const sizeBuckets = { '<5mm': 0, '5-6mm': 0, '6-7mm': 0, '7-8mm': 0, '>8mm': 0 }
  beanLog.forEach(b => {
    const s = b.size_mm || 0
    if      (s < 5)  sizeBuckets['<5mm']++
    else if (s < 6)  sizeBuckets['5-6mm']++
    else if (s < 7)  sizeBuckets['6-7mm']++
    else if (s < 8)  sizeBuckets['7-8mm']++
    else             sizeBuckets['>8mm']++
  })
  const sizeData = Object.entries(sizeBuckets).map(([k, v]) => ({ range: k, count: v }))

  /* ── Color name frequency ── */
  const colorFreq = {}
  beanLog.forEach(b => {
    if (b.color_name) colorFreq[b.color_name] = (colorFreq[b.color_name] || 0) + 1
  })
  const colorData = Object.entries(colorFreq)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([k, v]) => ({ name: k, count: v }))

  /* ── Defect breakdown ── */
  const defectFreq = {}
  beanLog.forEach(b => {
    (b.defects || []).forEach(d => {
      defectFreq[d] = (defectFreq[d] || 0) + 1
    })
  })
  const defectData = Object.entries(defectFreq)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => ({ type: k, count: v }))

  const isRunning = stats.status === 'running'

  return (
    <div className="page admin-page">

      {/* ── Page header ── */}
      <div className="admin-page-header">
        <div>
          <h2 className="admin-title">📊 Admin Dashboard</h2>
          <p className="admin-subtitle">
            Real-time bean data analysis — all data flows live from the Operator Dashboard
          </p>
        </div>
        <div className="admin-header-badges">
          <span className={`admin-live-badge ${isRunning ? 'live' : 'idle'}`}>
            <span className="admin-live-dot" />
            {isRunning ? 'Live' : 'Idle'}
          </span>
          <span className="admin-session-badge">
            Total: {total.toLocaleString()} beans
          </span>
        </div>
      </div>

      {/* ══ ROW 1 — KPI STATS ══ */}
      <div className="admin-kpi-grid">
        <AdminStat icon="📦" label="Total Detected"   value={total.toLocaleString()}           color="var(--coffee-light)" sub="This session" />
        <AdminStat icon="🏆" label="Good Yield"        value={`${goodYield.toFixed(1)}%`}        color="var(--premium)"      sub="Grade 1–3 combined" />
        <AdminStat icon="⚡" label="Beans / min"       value={Math.round(stats.beans_per_minute || 0)} color="var(--grade1)" sub="Throughput rate" />
        <AdminStat icon="❌" label="Defect Rate"        value={`${defectRate.toFixed(1)}%`}       color={defectRate > 10 ? 'var(--danger)' : 'var(--text-muted)'} sub="Grade 4 beans" />
        <AdminStat icon="🎯" label="Avg Confidence"    value={`${avgConf.toFixed(1)}%`}           color="var(--grade2)"       sub="Last 20 detections" />
        <AdminStat icon="📷" label="Camera FPS"        value={`${stats.camera_fps || 0}`}         color="var(--info)"         sub="Frames per second" />
      </div>

      {/* ══ ROW 2 — GRADE DISTRIBUTION + TREND ══ */}
      <div className="admin-two-col" style={{ marginBottom: 20 }}>

        {/* Grade Distribution Pie */}
        <div className="neu-card admin-card">
          <SectionHeader icon="🥧" title="Grade Distribution" badge={`${total} beans`} />
          <div className="admin-pie-wrap">
            <ResponsiveContainer width="100%" height={200}>
              <PieChart>
                <Pie
                  data={pieData.length > 0 ? pieData : [{ name: 'No data', value: 1, color: '#333' }]}
                  cx="50%" cy="50%"
                  innerRadius={55} outerRadius={85}
                  paddingAngle={2} dataKey="value" stroke="none"
                >
                  {(pieData.length > 0 ? pieData : [{ color: '#333' }]).map((d, i) => (
                    <Cell key={i} fill={d.color} />
                  ))}
                </Pie>
                <Tooltip contentStyle={tooltipStyle()} />
              </PieChart>
            </ResponsiveContainer>

            {/* Centre */}
            <div className="admin-pie-centre">
              <div className="admin-pie-pct">{goodYield.toFixed(0)}%</div>
              <div className="admin-pie-sub">Good Yield</div>
            </div>
          </div>

          {/* Grade rows */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
            {GRADE_CFG.map(g => {
              const cnt = sc[g.key] || 0
              const pct = total > 0 ? (cnt / total * 100) : 0
              return (
                <div key={g.key} className="admin-grade-row">
                  <div className="admin-grade-dot" style={{ background: g.color }} />
                  <span className="admin-grade-label">{g.label}</span>
                  <div className="admin-grade-bar-wrap">
                    <div className="admin-grade-bar-track">
                      <div className="admin-grade-bar-fill" style={{ width: `${pct}%`, background: g.color }} />
                    </div>
                  </div>
                  <span className="admin-grade-pct" style={{ color: g.color }}>{pct.toFixed(1)}%</span>
                  <span className="admin-grade-cnt">{cnt.toLocaleString()}</span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Live trend — Good Yield vs Defect Rate */}
        <div className="neu-card admin-card">
          <SectionHeader icon="📈" title="Real-Time Yield vs Defect Trend" />
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={trend} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
              <XAxis dataKey="t" hide />
              <YAxis tick={{ fontSize: 10, fill: 'var(--chart-axis)' }} domain={[0, 100]} />
              <Tooltip contentStyle={tooltipStyle()} formatter={(v) => `${v}%`} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'var(--text-muted)' }} />
              <Line type="monotone" dataKey="goodYield"   stroke="#10b981" strokeWidth={2} dot={false} name="Good Yield %" />
              <Line type="monotone" dataKey="defectRate"  stroke="#ef4444" strokeWidth={2} dot={false} strokeDasharray="4 3" name="Defect Rate %" />
            </LineChart>
          </ResponsiveContainer>

          {/* Throughput trend */}
          <div style={{ marginTop: 16 }}>
            <div className="section-label" style={{ marginBottom: 6 }}>Throughput (beans/min)</div>
            <ResponsiveContainer width="100%" height={100}>
              <LineChart data={trend} margin={{ top: 2, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
                <XAxis dataKey="t" hide />
                <YAxis tick={{ fontSize: 9, fill: 'var(--chart-axis)' }} />
                <Tooltip contentStyle={tooltipStyle()} />
                <Line type="monotone" dataKey="bpm" stroke="#3b82f6" strokeWidth={2} dot={false} name="Beans/min" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* ══ ROW 3 — SIZE + COLOR + DEFECT ANALYSIS ══ */}
      <div className="admin-three-col" style={{ marginBottom: 20 }}>

        {/* Size Distribution */}
        <div className="neu-card admin-card">
          <SectionHeader icon="📏" title="Beans by Size" badge={`${beanLog.length} samples`} />
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={sizeData} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
              <XAxis dataKey="range" tick={{ fontSize: 10, fill: 'var(--chart-axis)' }} />
              <YAxis tick={{ fontSize: 10, fill: 'var(--chart-axis)' }} />
              <Tooltip contentStyle={tooltipStyle()} />
              <Bar dataKey="count" name="Beans" radius={[4, 4, 0, 0]}>
                {sizeData.map((_, i) => (
                  <Cell key={i} fill={['#8b5cf6','#3b82f6','#10b981','#f59e0b','#ef4444'][i % 5]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div style={{ marginTop: 8 }}>
            {sizeData.filter(s => s.count > 0).map(s => (
              <div key={s.range} className="admin-size-row">
                <span className="admin-size-label">{s.range}</span>
                <div className="admin-size-bar-track">
                  <div className="admin-size-bar-fill" style={{
                    width: `${beanLog.length > 0 ? (s.count / beanLog.length * 100) : 0}%`,
                  }} />
                </div>
                <span className="admin-size-cnt">{s.count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Color Distribution */}
        <div className="neu-card admin-card">
          <SectionHeader icon="🎨" title="Beans by Color" badge={`${beanLog.length} samples`} />
          {colorData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={colorData} layout="vertical" margin={{ top: 4, right: 8, left: 4, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 10, fill: 'var(--chart-axis)' }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 9, fill: 'var(--chart-axis)' }} width={100} />
                  <Tooltip contentStyle={tooltipStyle()} />
                  <Bar dataKey="count" name="Beans" radius={[0, 4, 4, 0]}>
                    {colorData.map((_, i) => (
                      <Cell key={i} fill={['#d4a76a','#a0785a','#6f4e37','#10b981','#f59e0b','#ef4444'][i % 6]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
              <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
                {colorData.map((c, i) => (
                  <div key={c.name} className="admin-color-row">
                    <div className="admin-color-swatch" style={{
                      background: ['#d4a76a','#a0785a','#6f4e37','#10b981','#f59e0b','#ef4444'][i % 6],
                    }} />
                    <span className="admin-color-name">{c.name}</span>
                    <span className="admin-color-cnt">{c.count}</span>
                    <span className="admin-color-pct">
                      {beanLog.length > 0 ? (c.count / beanLog.length * 100).toFixed(0) : 0}%
                    </span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="admin-empty">No color data yet — start sorting</div>
          )}
        </div>

        {/* Defect Analysis */}
        <div className="neu-card admin-card">
          <SectionHeader icon="⚠️" title="Defect Analysis" badge={`${sc.grade4 || 0} defects`} />

          {/* Summary */}
          <div className="admin-defect-summary">
            <div className="admin-defect-big">
              <span style={{ color: defectRate > 10 ? 'var(--danger)' : 'var(--success)' }}>
                {defectRate.toFixed(1)}%
              </span>
              <span>Defect Rate</span>
            </div>
            <div className="admin-defect-target">
              Target: ≤ 5%
              <span className={`admin-defect-status ${defectRate <= 5 ? 'ok' : 'warn'}`}>
                {defectRate <= 5 ? '✓ On target' : '⚠ Above target'}
              </span>
            </div>
          </div>

          {/* Defect type breakdown */}
          {defectData.length > 0 ? (
            <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div className="section-label" style={{ marginBottom: 4 }}>Defect Types</div>
              {defectData.map(d => (
                <div key={d.type} className="admin-defect-row">
                  <span className="admin-defect-type">{d.type}</span>
                  <div className="admin-defect-bar-track">
                    <div className="admin-defect-bar-fill" style={{
                      width: `${defectData[0].count > 0 ? (d.count / defectData[0].count * 100) : 0}%`,
                    }} />
                  </div>
                  <span className="admin-defect-cnt">{d.count}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="admin-empty" style={{ marginTop: 16 }}>
              No defect data yet
            </div>
          )}

          {/* Confidence gauge */}
          <div style={{ marginTop: 16 }}>
            <div className="section-label" style={{ marginBottom: 6 }}>Detection Accuracy</div>
            <div className="admin-conf-bar-track">
              <div className="admin-conf-bar-fill" style={{ width: `${avgConf}%` }} />
            </div>
            <div className="admin-conf-labels">
              <span>0%</span>
              <span style={{ fontWeight: 700, color: avgConf >= 80 ? 'var(--success)' : 'var(--warning)' }}>
                {avgConf.toFixed(1)}% avg
              </span>
              <span>100%</span>
            </div>
          </div>
        </div>
      </div>

      {/* ══ ROW 4 — SORTING RESULTS + BEAN HISTORY ══ */}
      <div className="admin-two-col" style={{ marginBottom: 20 }}>

        {/* Sorting Results */}
        <div className="neu-card admin-card">
          <SectionHeader icon="🗂️" title="Sorting Results" badge="Current session" />
          <div className="admin-sort-grid">
            {GRADE_CFG.map(g => {
              const cnt = sc[g.key] || 0
              const pct = total > 0 ? (cnt / total * 100) : 0
              return (
                <div key={g.key} className="admin-sort-bin" style={{ borderColor: g.color + '40' }}>
                  <div className="admin-sort-bin-header" style={{ color: g.color }}>
                    {g.label}
                  </div>
                  <div className="admin-sort-bin-count" style={{ color: g.color }}>
                    {cnt.toLocaleString()}
                  </div>
                  <div className="admin-sort-bin-pct">{pct.toFixed(1)}%</div>
                  <div className="admin-sort-bin-bar">
                    <div style={{ width: `${pct}%`, background: g.color, height: '100%', borderRadius: 3, transition: 'width 0.6s ease' }} />
                  </div>
                  <div className="admin-sort-bin-label">Bin {g.key.replace('grade', '')}</div>
                </div>
              )
            })}
          </div>

          {/* Session summary stats */}
          <div className="admin-session-stats">
            <div className="admin-session-stat">
              <span>Total Sorted</span>
              <strong>{total.toLocaleString()}</strong>
            </div>
            <div className="admin-session-stat">
              <span>Good (G1+G2+G3)</span>
              <strong style={{ color: 'var(--success)' }}>
                {((sc.grade1 || 0) + (sc.grade2 || 0) + (sc.grade3 || 0)).toLocaleString()}
              </strong>
            </div>
            <div className="admin-session-stat">
              <span>Defective</span>
              <strong style={{ color: 'var(--danger)' }}>{(sc.grade4 || 0).toLocaleString()}</strong>
            </div>
            <div className="admin-session-stat">
              <span>Yield</span>
              <strong style={{ color: goodYield >= 90 ? 'var(--success)' : 'var(--warning)' }}>
                {goodYield.toFixed(1)}%
              </strong>
            </div>
          </div>
        </div>

        {/* Grade count trend over time */}
        <div className="neu-card admin-card">
          <SectionHeader icon="📉" title="Grade Count Trend" badge="Last 40 ticks" />
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trend} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
              <XAxis dataKey="t" hide />
              <YAxis tick={{ fontSize: 10, fill: 'var(--chart-axis)' }} />
              <Tooltip contentStyle={tooltipStyle()} />
              <Legend wrapperStyle={{ fontSize: 10, color: 'var(--text-muted)' }} />
              <Line type="monotone" dataKey="g1" stroke="#10b981" strokeWidth={1.5} dot={false} name="Grade 1" />
              <Line type="monotone" dataKey="g2" stroke="#3b82f6" strokeWidth={1.5} dot={false} name="Grade 2" />
              <Line type="monotone" dataKey="g3" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="Grade 3" />
              <Line type="monotone" dataKey="g4" stroke="#ef4444" strokeWidth={1.5} dot={false} strokeDasharray="4 2" name="Grade 4" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ══ ROW 5 — BEAN HISTORY TABLE ══ */}
      <div className="neu-card admin-card" style={{ marginBottom: 20 }}>
        <SectionHeader icon="🕐" title="Recent Bean Detections" badge={`Last ${beanLog.length} beans`} />
        <div style={{ overflowX: 'auto', marginTop: 8 }}>
          <table className="neu-table admin-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Time</th>
                <th>Grade</th>
                <th>Color</th>
                <th>Size</th>
                <th>Confidence</th>
                <th>Defects</th>
                <th>Bin</th>
              </tr>
            </thead>
            <tbody>
              {beanLog.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px' }}>
                    No beans detected yet — start the sorting system
                  </td>
                </tr>
              ) : beanLog.slice(0, 30).map((b, i) => {
                const cfg = GRADE_CFG.find(g => g.label.startsWith(b.grade || ''))
                const color = cfg?.color || '#94a3b8'
                return (
                  <tr key={i}>
                    <td className="td-mono" style={{ color: 'var(--text-muted)' }}>{beanLog.length - i}</td>
                    <td className="td-mono" style={{ fontSize: '0.68rem' }}>{b.ts}</td>
                    <td>
                      <span className="admin-grade-pill" style={{ background: color + '22', color }}>
                        {b.grade || '—'}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.72rem' }}>{b.color_name || '—'}</td>
                    <td className="td-mono">{b.size_mm ? `${b.size_mm} mm` : '—'}</td>
                    <td>
                      <div className="admin-conf-mini-bar">
                        <div style={{
                          width: `${b.confidence || 0}%`,
                          background: (b.confidence || 0) >= 80 ? '#10b981' : '#f59e0b',
                          height: '100%', borderRadius: 2,
                        }} />
                      </div>
                      <span className="td-mono" style={{ fontSize: '0.68rem', marginLeft: 4 }}>
                        {(b.confidence || 0).toFixed(0)}%
                      </span>
                    </td>
                    <td style={{ fontSize: '0.68rem', color: 'var(--danger)' }}>
                      {(b.defects || []).join(', ') || <span style={{ color: 'var(--text-muted)' }}>none</span>}
                    </td>
                    <td className="td-mono" style={{ color }}>
                      Bin {(b.recommended_bin || '').replace('grade', '')}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ══ ROW 6 — SESSION HISTORY ══ */}
      <div className="neu-card admin-card">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <SectionHeader icon="📋" title="Session History" badge={`${sessions.length} sessions`} />
          <button className="neu-btn neu-btn-sm" onClick={fetchSessions}>↻ Refresh</button>
        </div>
        <div style={{ overflowX: 'auto' }}>
          <table className="neu-table admin-table">
            <thead>
              <tr>
                <th>Session</th>
                <th>Started</th>
                <th>Status</th>
                <th>Total</th>
                <th>Grade 1</th>
                <th>Grade 2</th>
                <th>Grade 3</th>
                <th>Defects</th>
                <th>Yield</th>
              </tr>
            </thead>
            <tbody>
              {sessions.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '20px' }}>
                    No sessions yet
                  </td>
                </tr>
              ) : sessions.map(s => {
                const tot   = s.total_beans || 0
                const defects = s.grade4_count || 0
                const good  = tot - defects
                const yld   = tot > 0 ? (good / tot * 100) : 0
                return (
                  <tr key={s.session_id}>
                    <td className="td-mono">#{s.session_id}</td>
                    <td style={{ fontSize: '0.68rem' }}>
                      {s.started_at ? new Date(s.started_at).toLocaleString() : '—'}
                    </td>
                    <td>
                      <span style={{
                        fontSize: '0.65rem', fontWeight: 700,
                        padding: '2px 8px', borderRadius: 20,
                        background: s.is_active ? 'rgba(16,185,129,0.15)' : 'rgba(148,163,184,0.12)',
                        color: s.is_active ? 'var(--success)' : 'var(--text-muted)',
                      }}>
                        {s.is_active ? 'Active' : 'Closed'}
                      </span>
                    </td>
                    <td className="td-mono">{tot.toLocaleString()}</td>
                    <td className="td-mono" style={{ color: '#10b981' }}>{(s.grade1_count || 0).toLocaleString()}</td>
                    <td className="td-mono" style={{ color: '#3b82f6' }}>{(s.grade2_count || 0).toLocaleString()}</td>
                    <td className="td-mono" style={{ color: '#f59e0b' }}>{(s.grade3_count || 0).toLocaleString()}</td>
                    <td className="td-mono" style={{ color: '#ef4444' }}>{defects.toLocaleString()}</td>
                    <td>
                      <span style={{
                        fontFamily: 'JetBrains Mono, monospace',
                        fontSize: '0.72rem',
                        fontWeight: 700,
                        color: yld >= 90 ? 'var(--success)' : yld >= 70 ? 'var(--warning)' : 'var(--danger)',
                      }}>
                        {yld.toFixed(1)}%
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  )
}
