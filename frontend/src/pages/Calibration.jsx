import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../services/api'

const GRADES = [
  { key: 'grade1', label: 'Grade 1', color: '#16a34a' },
  { key: 'grade2', label: 'Grade 2', color: '#2563eb' },
  { key: 'grade3', label: 'Grade 3', color: '#d97706' },
  { key: 'grade4', label: 'Grade 4', color: '#dc2626' },
]

export default function Calibration({ frame, onComplete }) {
  const imageRef = useRef(null)
  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const mediaRef = useRef(null)
  const navigate = useNavigate()
  const [samples, setSamples] = useState({})
  const [selected, setSelected] = useState('grade1')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [point, setPoint] = useState(null)
  const [streamReady, setStreamReady] = useState(false)
  const [browserCamera, setBrowserCamera] = useState(false)
  const [lastCapture, setLastCapture] = useState(null)

  useEffect(() => {
    let active = true
    if (navigator.mediaDevices?.getUserMedia) {
      navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
        .catch(() => navigator.mediaDevices.getUserMedia({ video: true, audio: false }))
        .then(stream => {
          if (!active) { stream.getTracks().forEach(track => track.stop()); return }
          mediaRef.current = stream
          if (videoRef.current) videoRef.current.srcObject = stream
          setBrowserCamera(true)
        })
        .catch(() => { if (active) setBrowserCamera(false) })
    }
    return () => {
      active = false
      mediaRef.current?.getTracks().forEach(track => track.stop())
      mediaRef.current = null
    }
  }, [])

  useEffect(() => {
    api.getColorCalibration()
      .then(r => setSamples(r.samples || {}))
      .catch(e => setError(`Calibration API unavailable (${e.message}). Restart the backend so it loads the calibration endpoints.`))
  }, [])

  const capture = async (event) => {
    const source = browserCamera ? videoRef.current : imageRef.current
    const rect = source.getBoundingClientRect()
    const x = (event.clientX - rect.left) / rect.width
    const y = (event.clientY - rect.top) / rect.height
    setPoint({ x: event.clientX - rect.left, y: event.clientY - rect.top, color: current?.color || '#fff' })
    setBusy(true)
    setError('')
    try {
      let result
      if (browserCamera) {
        const video = videoRef.current
        const canvas = canvasRef.current
        const width = video.videoWidth, height = video.videoHeight
        const boxWidth = rect.width, boxHeight = rect.height
        const scale = Math.min(boxWidth / width, boxHeight / height)
        const shownWidth = width * scale, shownHeight = height * scale
        const offsetX = (boxWidth - shownWidth) / 2, offsetY = (boxHeight - shownHeight) / 2
        const px = Math.max(0, Math.min(width - 1, Math.round((event.clientX - rect.left - offsetX) / scale)))
        const py = Math.max(0, Math.min(height - 1, Math.round((event.clientY - rect.top - offsetY) / scale)))
        canvas.width = width; canvas.height = height
        const context = canvas.getContext('2d', { willReadFrequently: true })
        context.drawImage(video, 0, 0, width, height)
        const patch = context.getImageData(Math.max(0, px - 2), Math.max(0, py - 2), Math.min(5, width - Math.max(0, px - 2)), Math.min(5, height - Math.max(0, py - 2))).data
        const channels = [[], [], []]
        for (let i = 0; i < patch.length; i += 4) {
          channels[0].push(patch[i]); channels[1].push(patch[i + 1]); channels[2].push(patch[i + 2])
        }
        const median = values => values.sort((a, b) => a - b)[Math.floor(values.length / 2)]
        const hex = `#${channels.map(values => median(values).toString(16).padStart(2, '0')).join('')}`
        result = await api.captureColorHex(selected, hex)
      } else {
        result = await api.captureColorSample(selected, x, y)
      }
      setSamples(result.samples)
      setLastCapture({ grade: current?.label || selected, hex: result.hex })
      const next = GRADES.find(g => !result.samples[g.key])
      if (next) setSelected(next.key)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const finish = async () => {
    setBusy(true)
    setError('')
    try {
      await api.completeColorCalibration()
      onComplete?.()
      navigate('/dashboard')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const complete = GRADES.every(g => samples[g.key])
  const current = GRADES.find(g => g.key === selected)

  return (
    <div className="page" style={{ maxWidth: 1000, margin: '0 auto' }}>
      <div className="page-header">
        <h2>Camera color calibration</h2>
        <p>Place one representative sample bean for each grade under the camera. Select its grade, then click the bean in the live image. The system reads a small area around the point and saves only its median hex color.</p>
      </div>

      <div className="neu-card" style={{ padding: 18 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 14 }}>
          {GRADES.map(g => (
            <button key={g.key} onClick={() => setSelected(g.key)} className="neu-btn"
              aria-label={`Select ${g.label} to ${samples[g.key] ? 'update' : 'capture'} its color`}
              style={{ border: selected === g.key ? `2px solid ${g.color}` : undefined, display: 'flex', gap: 8, alignItems: 'center' }}>
              <span style={{ width: 9, height: 9, borderRadius: '50%', background: g.color }} />
              {g.label}{samples[g.key] ? ` · ${samples[g.key]} · Update` : ' · Pick color'}
            </button>
          ))}
        </div>

        <div style={{ position: 'relative', width: '100%', aspectRatio: '16 / 9', minHeight: 260, overflow: 'hidden', cursor: streamReady && !busy ? 'crosshair' : 'default', background: '#111', lineHeight: 0 }}>
          <video ref={videoRef} autoPlay muted playsInline onLoadedData={() => setStreamReady(true)}
            onClick={streamReady && !busy ? capture : undefined}
            style={{ display: browserCamera ? 'block' : 'none', width: '100%', height: '100%', objectFit: 'contain' }} />
          <img ref={imageRef} src={`${api.streamUrl()}?calibration=${Date.now()}`} alt="Live camera calibration view"
            onLoad={() => { if (!browserCamera) setStreamReady(true) }} onError={() => { if (!browserCamera) setStreamReady(false) }}
            onClick={!browserCamera && streamReady && !busy ? capture : undefined}
            style={{ display: browserCamera ? 'none' : 'block', width: '100%', height: '100%', objectFit: 'contain' }} />
          <canvas ref={canvasRef} style={{ display: 'none' }} />
          {!streamReady && <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: '#fff', lineHeight: 1.5, padding: 24, textAlign: 'center' }}>
            <div><div style={{ fontWeight: 700, marginBottom: 6 }}>Waiting for camera image</div>
              <div style={{ fontSize: '0.8rem', opacity: 0.8 }}>Check that the camera is connected, then wait for the live feed.</div></div>
          </div>}
          {point && <span style={{ pointerEvents: 'none', position: 'absolute', left: point.x, top: point.y, width: 18, height: 18, border: `3px solid ${point.color}`, borderRadius: '50%', transform: 'translate(-50%,-50%)' }} />}
        </div>
        <div style={{ marginTop: 10, color: 'var(--text-secondary)', fontSize: '0.78rem' }}>
          Selected: <strong style={{ color: current?.color }}>{current?.label}</strong>. Click the bean in the camera to {samples[selected] ? 'update its saved hex color' : 'capture its hex color'}. Select any grade above to pick or update it.
        </div>

        {lastCapture && <div role="status" style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 12, padding: '10px 12px', borderRadius: 10, background: 'rgba(34,197,94,0.08)' }}>
          <span style={{ width: 22, height: 22, borderRadius: 6, background: lastCapture.hex, border: '1px solid rgba(0,0,0,0.15)' }} />
          <span><strong>{lastCapture.grade} captured:</strong> <code>{lastCapture.hex}</code></span>
        </div>}

        {error && <div role="alert" style={{ color: 'var(--danger)', marginTop: 10 }}>{error}</div>}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16, gap: 12, flexWrap: 'wrap' }}>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>{GRADES.filter(g => samples[g.key]).length} of 4 grade colors captured</span>
          <button className="neu-btn" disabled={!complete || busy} onClick={finish}
            style={{ opacity: !complete || busy ? 0.5 : 1, color: 'var(--success)', fontWeight: 700 }}>
            {busy ? 'Saving…' : 'Finish calibration and enable Start'}
          </button>
        </div>
      </div>
    </div>
  )
}
