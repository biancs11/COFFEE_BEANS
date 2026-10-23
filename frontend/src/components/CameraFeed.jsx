import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../services/api'

const GRADE_COLORS = {
  'Grade 1': '#10b981',
  'Grade 2': '#3b82f6',
  'Grade 3': '#f59e0b',
  'Grade 4': '#ef4444',
}

export default function CameraFeed({ frame, isRunning, lastBean }) {
  const navigate = useNavigate()
  const videoRef = useRef(null)
  const sampleCanvasRef = useRef(null)
  const mediaRef = useRef(null)
  const frameUploadBusy = useRef(false)
  const [useLaptopCamera, setUseLaptopCamera] = useState(true)
  const [laptopCameraReady, setLaptopCameraReady] = useState(false)
  const [laptopCameraError, setLaptopCameraError] = useState('')
  const [previewBean, setPreviewBean] = useState(null)
  const [pinnedColor, setPinnedColor] = useState(null)
  const [useStream, setUseStream] = useState(false)
  const [imgError,  setImgError]  = useState(false)
  const [mjpegKey,  setMjpegKey]  = useState(0)

  useEffect(() => {
    let active = true
    const openCamera = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setLaptopCameraError('Browser camera access is unavailable. Open the app from localhost or HTTPS.')
        return
      }
      try {
        let stream
        try {
          stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
        } catch (_) {
          stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        }
        if (!active) { stream.getTracks().forEach(track => track.stop()); return }
        mediaRef.current = stream
        if (videoRef.current) videoRef.current.srcObject = stream
        setLaptopCameraError('')
      } catch (error) {
        if (active) setLaptopCameraError(error.name === 'NotAllowedError'
          ? 'Allow camera access in your browser to show the laptop camera.'
          : `Laptop camera could not start: ${error.message}`)
      }
    }
    openCamera()
    return () => {
      active = false
      mediaRef.current?.getTracks().forEach(track => track.stop())
      mediaRef.current = null
    }
  }, [])

  useEffect(() => {
    if (useLaptopCamera && videoRef.current && mediaRef.current) {
      videoRef.current.srcObject = mediaRef.current
    }
  }, [useLaptopCamera])

  useEffect(() => {
    if (!useLaptopCamera || !laptopCameraReady) return undefined
    const canvas = document.createElement('canvas')
    canvas.width = 640
    canvas.height = 480
    const context = canvas.getContext('2d')
    const timer = setInterval(() => {
      const video = videoRef.current
      if (!video || video.readyState < 2 || frameUploadBusy.current) return
      context.drawImage(video, 0, 0, canvas.width, canvas.height)
      canvas.toBlob(async blob => {
        if (!blob) return
        frameUploadBusy.current = true
        try {
          const result = await api.submitBrowserFrame(blob)
          if (!isRunning && result.preview) setPreviewBean(result.beans?.at(-1) || null)
        } catch (_) {}
        finally { frameUploadBusy.current = false }
      }, 'image/jpeg', 0.78)
    }, isRunning ? 250 : 700)
    return () => clearInterval(timer)
  }, [useLaptopCamera, laptopCameraReady, isRunning])

  useEffect(() => {
    if (isRunning) setPreviewBean(null)
  }, [isRunning])

  const sampleCameraColor = (event) => {
    const video = videoRef.current
    if (!useLaptopCamera || !laptopCameraReady || !video || video.readyState < 2) return
    const width = video.videoWidth
    const height = video.videoHeight
    if (!width || !height) return

    const rect = event.currentTarget.getBoundingClientRect()
    const scale = Math.max(rect.width / width, rect.height / height) // video uses object-fit: cover
    const shownWidth = width * scale
    const shownHeight = height * scale
    const cropX = (shownWidth - rect.width) / 2
    const cropY = (shownHeight - rect.height) / 2
    const px = Math.max(0, Math.min(width - 1, Math.round((event.clientX - rect.left + cropX) / scale)))
    const py = Math.max(0, Math.min(height - 1, Math.round((event.clientY - rect.top + cropY) / scale)))
    const canvas = sampleCanvasRef.current
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d', { willReadFrequently: true })
    context.drawImage(video, 0, 0, width, height)
    const x0 = Math.max(0, px - 2), y0 = Math.max(0, py - 2)
    const patch = context.getImageData(x0, y0, Math.min(5, width - x0), Math.min(5, height - y0)).data
    const channels = [[], [], []]
    for (let i = 0; i < patch.length; i += 4) {
      channels[0].push(patch[i]); channels[1].push(patch[i + 1]); channels[2].push(patch[i + 2])
    }
    const median = values => values.sort((a, b) => a - b)[Math.floor(values.length / 2)]
    const rgb = channels.map(median)
    const hex = `#${rgb.map(value => value.toString(16).padStart(2, '0')).join('').toUpperCase()}`
    setPinnedColor({ rgb, hex })
  }

  // Reset errors when system restarts
  useEffect(() => {
    if (!isRunning) setImgError(false)
  }, [isRunning])

  const visibleBean = isRunning ? lastBean : previewBean
  const gradeColor = visibleBean?.grade
    ? (GRADE_COLORS[visibleBean.grade] || '#94a3b8')
    : '#94a3b8'
  const detectedHex = visibleBean
    ? `#${[visibleBean.color_r, visibleBean.color_g, visibleBean.color_b].map(v => Number(v).toString(16).padStart(2, '0')).join('').toUpperCase()}`
    : null
  const cameraActive = useLaptopCamera ? laptopCameraReady : isRunning

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className={`status-dot ${cameraActive ? 'running' : 'stopped'}`} />
          <span className="text-xs text-muted" style={{ fontWeight: 600 }}>
            {useLaptopCamera ? (laptopCameraReady ? 'Laptop camera active' : 'Opening laptop camera…') : (isRunning ? 'System camera active' : 'System camera inactive')}
          </span>
          {useLaptopCamera && laptopCameraReady && (
            <span className="text-xs text-muted">Click the camera image to read a color.</span>
          )}
          {isRunning && (
            <span style={{
              background: 'rgba(220,38,38,0.85)', color: '#fff',
              fontSize: '0.58rem', fontWeight: 700,
              padding: '2px 7px', borderRadius: 4,
              letterSpacing: '0.1em', fontFamily: 'monospace',
            }}>● REC</span>
          )}
        </div>

        {/* Mode toggle */}
        <div style={{ display: 'flex', gap: 4 }}>
          <button
            className={`neu-btn neu-btn-sm${useLaptopCamera ? ' neu-btn-primary' : ''}`}
            onClick={() => setUseLaptopCamera(true)}
            style={{ padding: '5px 10px', fontSize: '0.68rem' }}
            title="Use the laptop camera in this browser"
          >
            Laptop Camera
          </button>
          <button
            className={`neu-btn neu-btn-sm${!useLaptopCamera && !useStream ? ' neu-btn-primary' : ''}`}
            onClick={() => { setUseLaptopCamera(false); setUseStream(false) }}
            style={{ padding: '5px 10px', fontSize: '0.68rem' }}
            title="OpenCV annotated feed from the backend camera"
          >
            WS Annotated
          </button>
          <button
            className={`neu-btn neu-btn-sm${!useLaptopCamera && useStream ? ' neu-btn-primary' : ''}`}
            onClick={() => { setUseLaptopCamera(false); setUseStream(true); setImgError(false); setMjpegKey(k => k + 1) }}
            style={{ padding: '5px 10px', fontSize: '0.68rem' }}
            title="Raw MJPEG stream from the backend camera"
          >
            MJPEG Stream
          </button>
        </div>
      </div>

      {/* Viewport */}
      <div className="camera-view" onClick={sampleCameraColor}
        style={{ borderRadius: 'var(--r-lg)', cursor: useLaptopCamera && laptopCameraReady ? 'crosshair' : undefined }}>

        {useLaptopCamera && (
          <>
            <video ref={videoRef} autoPlay muted playsInline
              onLoadedData={() => setLaptopCameraReady(true)}
              onError={() => { setLaptopCameraReady(false); setLaptopCameraError('Laptop camera stream stopped. Check browser camera permission.') }}
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: isRunning && frame ? 'none' : 'block' }} />
            {isRunning && frame && <img src={frame} alt="Laptop camera with bean detection overlay"
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />}
            {!laptopCameraReady && (
              <div className="camera-offline">
                <span style={{ fontSize: 48, opacity: 0.25 }}>📷</span>
                <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'center', padding: '0 20px' }}>
                  {laptopCameraError || 'Waiting for laptop camera permission…'}
                </span>
                {!laptopCameraError && <div style={{ width: 24, height: 24, border: '3px solid rgba(100,100,100,0.2)', borderTopColor: 'var(--coffee-light)', borderRadius: '50%', animation: 'cam-spin 0.8s linear infinite' }} />}
              </div>
            )}
          </>
        )}

        {/* WS Annotated — OpenCV frame with detection boxes */}
        {!useLaptopCamera && !useStream && isRunning && frame && (
          <img
            src={frame}
            alt="Annotated feed"
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
          />
        )}

        {/* WS Annotated — waiting for first frame */}
        {!useLaptopCamera && !useStream && isRunning && !frame && (
          <div className="camera-offline">
            <span style={{ fontSize: 52, opacity: 0.2 }}>📷</span>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
              Waiting for annotated frame…
            </span>
            <div style={{
              width: 28, height: 28,
              border: '3px solid rgba(100,100,100,0.2)',
              borderTopColor: 'var(--coffee-light)',
              borderRadius: '50%',
              animation: 'cam-spin 0.8s linear infinite',
            }} />
          </div>
        )}

        {/* MJPEG stream */}
        {!useLaptopCamera && useStream && isRunning && !imgError && (
          <img
            key={mjpegKey}
            src={`${api.streamUrl()}?t=${mjpegKey}`}
            alt="MJPEG stream"
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            onError={() => setImgError(true)}
          />
        )}

        {/* MJPEG error */}
        {!useLaptopCamera && useStream && isRunning && imgError && (
          <div className="camera-offline">
            <span style={{ fontSize: 40, opacity: 0.25 }}>⚠️</span>
            <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textAlign: 'center', padding: '0 20px' }}>
              Cannot reach MJPEG stream.<br />Check the phone IP Webcam app.
            </span>
            <button className="neu-btn neu-btn-sm"
              onClick={() => { setImgError(false); setMjpegKey(k => k + 1) }}
              style={{ marginTop: 8 }}>↻ Retry</button>
          </div>
        )}

        {/* System not running */}
        {!useLaptopCamera && !isRunning && (
          <div className="camera-offline">
            <span style={{ fontSize: 52, opacity: 0.2 }}>📷</span>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)', textAlign: 'center', padding: '0 16px' }}>
              Open the laptop camera and pin a bean in Color Calibration before starting the sorter.
            </span>
            <button className="neu-btn neu-btn-primary" onClick={() => navigate('/calibration')}>
              Open Color Calibration
            </button>
          </div>
        )}

        {/* Overlays — only when running */}
        {(isRunning || (useLaptopCamera && laptopCameraReady)) && (
          <>
            {/* Corner brackets */}
            {[
              { top: 10,    left: 10,  borderTop:    '2px solid', borderLeft:   '2px solid' },
              { top: 10,    right: 10, borderTop:    '2px solid', borderRight:  '2px solid' },
              { bottom: 10, left: 10,  borderBottom: '2px solid', borderLeft:   '2px solid' },
              { bottom: 10, right: 10, borderBottom: '2px solid', borderRight:  '2px solid' },
            ].map((s, i) => (
              <div key={i} style={{
                position: 'absolute', width: 22, height: 22,
                borderColor: 'rgba(55,145,85,0.65)', ...s,
              }} />
            ))}

            {/* CAM label */}
            <div style={{
              position: 'absolute', top: 10, left: 38,
              background: 'rgba(0,0,0,0.6)', color: '#10b981',
              fontSize: '0.58rem', fontWeight: 700,
              padding: '2px 8px', borderRadius: 4, fontFamily: 'monospace',
              letterSpacing: '0.08em',
            }}>CAM-01</div>

            {/* Mode indicator */}
            <div style={{
              position: 'absolute', top: 10, right: 38,
              background: 'rgba(0,0,0,0.55)',
              fontSize: '0.55rem', fontWeight: 600,
              padding: '2px 7px', borderRadius: 4, fontFamily: 'monospace',
              color: useStream ? '#f59e0b' : '#10b981',
            }}>
              {useStream ? 'MJPEG' : 'WS'}
            </div>

            {/* Last bean color and grade HUD */}
            {pinnedColor ? (
              <div role="status" style={{
                position: 'absolute', bottom: 8, left: 10,
                padding: '6px 10px', borderRadius: 6,
                background: 'rgba(0,0,0,0.72)', color: '#fff',
                display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.66rem',
              }}>
                <span style={{ width: 18, height: 18, borderRadius: 4, background: `rgb(${pinnedColor.rgb.join(',')})`, border: '1px solid #fff' }} />
                Pinned color <code>{pinnedColor.hex}</code>
              </div>
            ) : visibleBean ? (
              <div style={{
                position: 'absolute', bottom: 0, left: 0, right: 0,
                background: 'linear-gradient(transparent, rgba(0,0,0,0.75))',
                padding: '20px 14px 10px',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{
                    background: gradeColor, borderRadius: 4,
                    padding: '2px 9px', fontSize: '0.66rem', fontWeight: 700,
                    color: '#fff', textTransform: 'uppercase', letterSpacing: '0.06em',
                  }}>{visibleBean.grade}</div>
                  <span style={{ fontSize: '0.64rem', color: 'rgba(255,255,255,0.75)', fontFamily: 'monospace' }}>
                    {visibleBean.confidence?.toFixed(0)}% conf
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span aria-label={`Detected color ${detectedHex}`} style={{
                    width: 18, height: 18, borderRadius: 4, flexShrink: 0,
                    background: `rgb(${visibleBean.color_r},${visibleBean.color_g},${visibleBean.color_b})`,
                    border: '1px solid rgba(255,255,255,0.75)',
                  }} />
                  <span style={{ fontSize: '0.65rem', color: '#fff', fontWeight: 700, lineHeight: 1.3 }}>
                    <span style={{ display: 'block', fontSize: '0.5rem', opacity: 0.7, letterSpacing: '0.06em' }}>DETECTED COLOR</span>
                    {visibleBean.color_name} <span style={{ fontFamily: 'monospace', opacity: 0.9 }}>{detectedHex}</span>
                    <span style={{ display: 'block', fontSize: '0.56rem', color: '#a7f3d0', marginTop: 2 }}>
                      CALIBRATION MATCH · {visibleBean.calibrated_grade?.replace('grade', 'Grade ') || 'Not configured'}
                      {visibleBean.calibrated_hex ? ` ${visibleBean.calibrated_hex}` : ''}
                    </span>
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 12 }}>
                  {visibleBean.size_mm != null && (
                    <span style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.6)', fontFamily: 'monospace' }}>
                      Ø {visibleBean.size_mm?.toFixed(1)} mm
                    </span>
                  )}
                  {visibleBean.recommended_bin && (
                    <span style={{ fontSize: '0.62rem', color: gradeColor, fontFamily: 'monospace', fontWeight: 700 }}>
                      → Bin {visibleBean.recommended_bin.replace('grade', '')}
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <div style={{
                position: 'absolute', bottom: 8, left: 10,
                padding: '5px 9px', borderRadius: 6,
                background: 'rgba(0,0,0,0.62)', color: '#fff',
                fontSize: '0.64rem',
              }}>
                Waiting for a bean to read its color…
              </div>
            )}
          </>
        )}
        <canvas ref={sampleCanvasRef} style={{ display: 'none' }} />
      </div>

      <style>{`@keyframes cam-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
