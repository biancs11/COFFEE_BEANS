/**
 * GradeCard — displays a single bean detection result with all attributes.
 */

const GRADE_META = {
  'Premium':   { color: 'var(--premium)',   cls: 'premium',   dot: '🟢', binLabel: 'Premium Bin'  },
  'Grade 1':   { color: 'var(--grade1)',    cls: 'grade_1',   dot: '🔵', binLabel: 'Grade 1 Bin'  },
  'Grade 2':   { color: 'var(--grade2)',    cls: 'grade_2',   dot: '🟡', binLabel: 'Grade 2 Bin'  },
  'Grade 3':   { color: 'var(--grade3)',    cls: 'grade_3',   dot: '🟣', binLabel: 'Grade 3 Bin'  },
  'Defective': { color: 'var(--defective)', cls: 'defective', dot: '🔴', binLabel: 'Defect Bin'   },
}

export default function GradeCard({ bean }) {
  if (!bean) {
    return (
      <div className="neu-inset flex flex-col items-center justify-center" style={{ minHeight: 120, gap: 8 }}>
        <span style={{ fontSize: 32, opacity: 0.3 }}>☕</span>
        <span className="text-xs text-muted">Waiting for detection…</span>
      </div>
    )
  }

  const meta = GRADE_META[bean.grade] || GRADE_META['Grade 3']
  const confColor = bean.confidence >= 90 ? 'var(--success)' : bean.confidence >= 75 ? 'var(--warning)' : 'var(--danger)'
  const confFill  = bean.confidence >= 90 ? 'fill-success' : bean.confidence >= 75 ? 'fill-grade2' : 'fill-defective'

  return (
    <div className="neu-card" style={{ padding: 18 }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div style={{
            width: 10, height: 10, borderRadius: '50%',
            background: meta.color,
            boxShadow: `0 0 8px ${meta.color}`,
          }} />
          <span className="font-bold" style={{ color: meta.color, fontSize: '0.9rem' }}>
            {bean.grade}
          </span>
        </div>
        <span className={`neu-badge badge-${meta.cls}`}>
          {meta.binLabel}
        </span>
      </div>

      {/* Color swatch + name */}
      <div className="flex items-center gap-3 mb-3">
        <div style={{
          width: 40, height: 40, borderRadius: 'var(--r-sm)',
          background: `rgb(${bean.color_r},${bean.color_g},${bean.color_b})`,
          boxShadow: 'var(--shadow-in)',
          flexShrink: 0,
        }} />
        <div>
          <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)' }}>
            {bean.color_name}
          </div>
          <div className="text-xs text-muted">{bean.roast_level}</div>
        </div>
        <div style={{ flex: 1 }} />
        <div style={{ textAlign: 'right' }}>
          <div className="font-mono font-bold" style={{ fontSize: '1rem', color: 'var(--text-primary)' }}>
            {bean.size_mm} mm
          </div>
          <div className="text-xs text-muted">diameter</div>
        </div>
      </div>

      {/* Confidence bar */}
      <div className="mb-3">
        <div className="flex justify-between text-xs text-muted mb-1">
          <span>AI Confidence</span>
          <span className="font-mono font-bold" style={{ color: confColor }}>{bean.confidence}%</span>
        </div>
        <div className="neu-progress-track">
          <div className={`neu-progress-fill ${confFill}`} style={{ width: `${bean.confidence}%` }} />
        </div>
      </div>

      {/* Attributes */}
      <div className="attr-row">
        <span className="attr-icon">🎨</span>
        <span className="attr-label">Hue / Sat / Val</span>
        <span className="attr-value font-mono" style={{ fontSize: '0.68rem' }}>
          {bean.hue.toFixed(0)} / {bean.saturation.toFixed(0)} / {bean.brightness.toFixed(0)}
        </span>
      </div>
      <div className="attr-row">
        <span className="attr-icon">📐</span>
        <span className="attr-label">Area (px)</span>
        <span className="attr-value font-mono">{bean.area_px.toLocaleString()}</span>
      </div>
      <div className="attr-row">
        <span className="attr-icon">🔍</span>
        <span className="attr-label">Defects</span>
        <span className="attr-value" style={{ color: bean.defects.length > 0 ? 'var(--danger)' : 'var(--success)', fontSize: '0.72rem' }}>
          {bean.defects.length > 0 ? bean.defects.join(', ') : 'None detected'}
        </span>
      </div>
      <div className="attr-row">
        <span className="attr-icon">🕐</span>
        <span className="attr-label">Timestamp</span>
        <span className="attr-value font-mono text-xs">{bean.timestamp}</span>
      </div>
    </div>
  )
}
