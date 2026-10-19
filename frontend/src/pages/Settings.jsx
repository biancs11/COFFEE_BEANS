import { useState, useEffect } from 'react'
import { api } from '../services/api'

export default function Settings({ onToast }) {
  const [form, setForm] = useState({
    conveyor_rpm:         180,
    sensitivity:          0.85,
    min_bean_area_px:     400,
    max_bean_area_px:     8000,
    ejection_duration_ms: 40,
    air_pressure_mpa:     0.6,
    auto_sort:            true,
  })
  const [ppm, setPpm] = useState(18.0)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.getSettings().then(s => setForm(s)).catch(() => {})
  }, [])

  const handleSave = async () => {
    setLoading(true)
    try {
      await api.updateSettings(form)
      onToast?.('Settings saved', 'success')
    } catch (e) {
      onToast?.(`Save failed: ${e.message}`, 'danger')
    } finally {
      setLoading(false)
    }
  }

  const handleCalibrate = async () => {
    try {
      await api.calibrate(ppm)
      onToast?.(`Calibration set to ${ppm} px/mm`, 'success')
    } catch (e) {
      onToast?.(`Calibration failed: ${e.message}`, 'danger')
    }
  }

  const set = (k, v) => setForm(prev => ({ ...prev, [k]: v }))

  return (
    <div className="page">
      <div className="page-header">
        <h2>⚙️ System Configuration</h2>
        <p>Adjust sorting parameters, detection sensitivity, and hardware settings.</p>
      </div>

      <div className="grid-2 mb-4">

        {/* Sorting settings */}
        <div className="neu-card">
          <div className="section-label mb-4">Sorting Parameters</div>

          <div className="mb-4">
            <div className="flex justify-between text-xs text-muted mb-2">
              <span>Conveyor Speed</span>
              <span className="font-mono font-bold">{form.conveyor_rpm} RPM</span>
            </div>
            <input type="range" className="neu-range" min={50} max={300} value={form.conveyor_rpm}
              onChange={e => set('conveyor_rpm', +e.target.value)} />
          </div>

          <div className="mb-4">
            <div className="flex justify-between text-xs text-muted mb-2">
              <span>Detection Sensitivity</span>
              <span className="font-mono font-bold">{(form.sensitivity * 100).toFixed(0)}%</span>
            </div>
            <input type="range" className="neu-range" min={0.5} max={1.0} step={0.01} value={form.sensitivity}
              onChange={e => set('sensitivity', +e.target.value)} />
          </div>

          <div className="mb-4">
            <div className="flex justify-between text-xs text-muted mb-2">
              <span>Ejection Duration</span>
              <span className="font-mono font-bold">{form.ejection_duration_ms} ms</span>
            </div>
            <input type="range" className="neu-range" min={10} max={100} value={form.ejection_duration_ms}
              onChange={e => set('ejection_duration_ms', +e.target.value)} />
          </div>

          <div className="mb-4">
            <div className="flex justify-between text-xs text-muted mb-2">
              <span>Min Bean Area (px)</span>
              <span className="font-mono font-bold">{form.min_bean_area_px}</span>
            </div>
            <input type="range" className="neu-range" min={100} max={2000} step={50} value={form.min_bean_area_px}
              onChange={e => set('min_bean_area_px', +e.target.value)} />
          </div>

          <div className="mb-4">
            <div className="flex justify-between text-xs text-muted mb-2">
              <span>Max Bean Area (px)</span>
              <span className="font-mono font-bold">{form.max_bean_area_px}</span>
            </div>
            <input type="range" className="neu-range" min={2000} max={20000} step={200} value={form.max_bean_area_px}
              onChange={e => set('max_bean_area_px', +e.target.value)} />
          </div>

          <div className="flex items-center justify-between mt-4">
            <div>
              <div className="text-sm" style={{ fontWeight: 600 }}>Auto-Sort</div>
              <div className="text-xs text-muted">Automatically fire ejector on defective beans</div>
            </div>
            <div
              className={`neu-toggle ${form.auto_sort ? 'on' : ''}`}
              onClick={() => set('auto_sort', !form.auto_sort)}
            />
          </div>
        </div>

        {/* Calibration + GPIO info */}
        <div className="flex flex-col gap-4">

          <div className="neu-card">
            <div className="section-label mb-3">Camera Calibration</div>
            <p className="text-xs text-muted mb-3" style={{ lineHeight: 1.6 }}>
              Measure a known object (e.g. 10mm coin) in pixels from a camera snapshot,
              then set pixels-per-mm: <strong>px_per_mm = measured_pixels / actual_mm</strong>
            </p>
            <div className="flex gap-3 items-center">
              <input
                type="number" className="neu-input" step={0.5} min={1} value={ppm}
                onChange={e => setPpm(+e.target.value)}
                style={{ width: 120 }}
              />
              <span className="text-xs text-muted">px / mm</span>
              <button className="neu-btn neu-btn-primary" onClick={handleCalibrate}>
                Apply Calibration
              </button>
            </div>
          </div>

          <div className="neu-card">
            <div className="section-label mb-3">GPIO Pin Map</div>
            <table className="neu-table">
              <thead><tr><th>Pin (BCM)</th><th>Function</th></tr></thead>
              <tbody>
                {[
                  ['GPIO 17', 'Solenoid Valve 1 — Defective ejector'],
                  ['GPIO 27', 'Solenoid Valve 2 — Premium gate'],
                  ['GPIO 22', 'Solenoid Valve 3 — Grade 1 gate'],
                  ['GPIO 23', 'Solenoid Valve 4 — Grade 2 gate'],
                  ['GPIO 24', 'Solenoid Valve 5 — Grade 3 gate'],
                  ['GPIO 25', 'Conveyor belt relay'],
                  ['GPIO 18', 'Air compressor relay'],
                ].map(([pin, fn]) => (
                  <tr key={pin}>
                    <td className="td-mono" style={{ color: 'var(--grade1)' }}>{pin}</td>
                    <td className="text-sm">{fn}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="neu-card">
            <div className="section-label mb-3">About</div>
            <div style={{ display: 'grid', gap: 6 }}>
              {[
                ['Platform',   'Raspberry Pi 5'],
                ['Camera',     'RPi Camera Module v2/v3'],
                ['Display',    'Waveshare LCD (touch)'],
                ['Language',   'Python 3.12 + FastAPI'],
                ['Frontend',   'React 18 + Vite'],
                ['Detection',  'OpenCV 4.9 (HSV + Contours)'],
                ['Stream',     'WebSocket + MJPEG'],
              ].map(([k, v]) => (
                <div key={k} className="neu-inset flex justify-between items-center">
                  <span className="text-xs text-muted">{k}</span>
                  <span className="font-mono" style={{ fontSize: '0.72rem', fontWeight: 600 }}>{v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <button className="neu-btn neu-btn-primary" onClick={handleSave} disabled={loading}>
        {loading ? '⏳ Saving…' : '💾 Save Settings'}
      </button>
    </div>
  )
}
