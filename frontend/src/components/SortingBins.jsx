import { useState, useEffect } from 'react'

const BINS = [
  { key: 'defective', label: 'Defective',  icon: '❌', color: 'var(--defective)', fill: 'fill-defective' },
  { key: 'premium',   label: 'Premium',    icon: '⭐', color: 'var(--premium)',   fill: 'fill-premium'   },
  { key: 'grade1',    label: 'Grade 1',    icon: '🔵', color: 'var(--grade1)',    fill: 'fill-grade1'    },
  { key: 'grade2',    label: 'Grade 2',    icon: '🟡', color: 'var(--grade2)',    fill: 'fill-grade2'    },
  { key: 'grade3',    label: 'Grade 3',    icon: '🟣', color: 'var(--grade3)',    fill: 'fill-grade3'    },
]

export default function SortingBins({ counts, lastBeanGrade }) {
  const [activeBin, setActiveBin] = useState(null)

  // Flash the active bin when a new bean is sorted
  useEffect(() => {
    if (!lastBeanGrade) return
    const key = lastBeanGrade.toLowerCase().replace(' ', '')
      .replace('grade1', 'grade1')
      .replace('grade2', 'grade2')
      .replace('grade3', 'grade3')
      .replace('premium', 'premium')
      .replace('defective', 'defective')
    setActiveBin(key)
    const t = setTimeout(() => setActiveBin(null), 500)
    return () => clearTimeout(t)
  }, [lastBeanGrade])

  const total = Object.values(counts).reduce((a, b) => a + b, 0)

  return (
    <div className="grid-5">
      {BINS.map(bin => {
        const count = counts[bin.key] || 0
        const pct   = total > 0 ? ((count / total) * 100).toFixed(1) : '0.0'
        const isActive = activeBin === bin.key

        return (
          <div key={bin.key} className={`bin-card ${isActive ? 'active' : ''}`}>
            <div className="bin-icon">{bin.icon}</div>
            <div className="bin-label" style={{ color: bin.color }}>{bin.label}</div>
            <div className="bin-count" style={{ color: bin.color }}>{count}</div>
            <div className="bin-pct">{pct}%</div>
            <div style={{ marginTop: 8 }}>
              <div className="neu-progress-track" style={{ height: 5 }}>
                <div
                  className={`neu-progress-fill ${bin.fill}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
