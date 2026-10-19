import CameraFeed from '../components/CameraFeed'
import GradeCard from '../components/GradeCard'

export default function Detection({ stats, lastBean, frame }) {
  const isRunning = stats.status === 'running'

  return (
    <div className="page">
      <div className="page-header">
        <h2>📷 Feature 1 — Bean Detection & Image Acquisition</h2>
        <p>
          Raspberry Pi Camera Module captures frames at up to {stats.camera_fps} fps.
          OpenCV detects individual beans via HSV masking and contour analysis,
          extracting bounding boxes, size, and color data in real time.
        </p>
      </div>

      {/* Stats row */}
      <div className="grid-4 mb-4">
        {[
          { icon: '📷', val: stats.beans_processed, label: 'Beans Detected',    v: 'coffee'   },
          { icon: '⚡', val: `${stats.camera_fps} fps`, label: 'Camera FPS',   v: 'grade1'   },
          { icon: '🔄', val: `${Math.round(stats.beans_per_minute)}/min`, label: 'Throughput', v: 'premium' },
          { icon: '🎯', val: `${stats.conveyor_rpm} RPM`, label: 'Conveyor',   v: 'grade2'   },
        ].map(s => (
          <div key={s.label} className={`stat-card ${s.v}`}>
            <div className={`stat-icon ${s.v}`}>{s.icon}</div>
            <div className="stat-info">
              <div className="stat-value font-mono">{s.val}</div>
              <div className="stat-label">{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="grid-2 mb-4">
        {/* Camera feed */}
        <div className="neu-card">
          <div className="section-label mb-3">Live Camera Feed</div>
          <CameraFeed frame={frame} isRunning={isRunning} />
        </div>

        {/* Latest detection */}
        <div className="flex flex-col gap-3">
          <div className="neu-card">
            <div className="section-label mb-3">Latest Detection Result</div>
            <GradeCard bean={lastBean} />
          </div>

          {/* Camera specs */}
          <div className="neu-card">
            <div className="section-label mb-3">Camera Hardware Specs</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {[
                ['Resolution', '5–12 MP'],
                ['Interface',  'CSI / USB3.0'],
                ['Frame Rate', '30–200 fps'],
                ['Lens',       'C-mount 8–12mm'],
                ['LED Light',  '10k–50k lux'],
                ['Color Temp', '5500–6500K'],
                ['Processor',  'Raspberry Pi 5'],
                ['Software',   'OpenCV / Python'],
              ].map(([k, v]) => (
                <div key={k} className="neu-inset">
                  <div className="text-xs text-muted">{k}</div>
                  <div className="font-mono" style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-primary)', marginTop: 2 }}>{v}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Recent beans table */}
      <div className="neu-card">
        <div className="section-label mb-3">Recent Detections</div>
        <div style={{ overflowX: 'auto' }}>
          <table className="neu-table">
            <thead>
              <tr>
                <th>#</th><th>Grade</th><th>Size</th><th>Color</th>
                <th>Confidence</th><th>Defects</th><th>Time</th>
              </tr>
            </thead>
            <tbody>
              {!lastBean && (
                <tr><td colSpan={7} className="text-center text-muted" style={{ padding: '24px 0' }}>No detections yet — start system</td></tr>
              )}
              {lastBean && (
                <tr>
                  <td className="td-mono">{lastBean.id}</td>
                  <td>
                    <span className={`grade-pill ${lastBean.grade.toLowerCase().replace(' ', '_')}`}>
                      {lastBean.grade}
                    </span>
                  </td>
                  <td className="td-mono">{lastBean.size_mm} mm</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <div style={{ width: 14, height: 14, borderRadius: 3, background: `rgb(${lastBean.color_r},${lastBean.color_g},${lastBean.color_b})`, flexShrink: 0 }} />
                      {lastBean.color_name}
                    </div>
                  </td>
                  <td className="td-mono">{lastBean.confidence}%</td>
                  <td style={{ color: lastBean.defects.length > 0 ? 'var(--danger)' : 'var(--success)' }}>
                    {lastBean.defects.length > 0 ? lastBean.defects.join(', ') : '—'}
                  </td>
                  <td className="td-mono text-muted">{lastBean.timestamp}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
