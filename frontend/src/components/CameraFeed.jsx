import { useState, useEffect } from 'react'
import { api } from '../services/api'

const GRADE_COLORS = {
  'Grade 1': '#10b981',
  'Grade 2': '#3b82f6',
  'Grade 3': '#f59e0b',
  'Grade 4': '#ef4444',
}

export default function CameraFeed({ frame, isRunning, lastBean }) {
  // Default to WS Annotated — shows OpenCV detection boxes
  const [useStream, setUseStream] = useState(false)
  const [imgError,  setImgError]  = useState(false)
  const [mjpegKey,  setMjpegKey]  = useState(0)

  // Reset errors when system restarts
  useEffect(() => {
    if (!isRunning) setImgError(false)
  }, [isRunning])

  const gradeColor = lastBean?.grade
    ? (GRADE_COLORS[lastBean.grade] || '#94a3b8')
    : '#94a3b8'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span className={`status-dot ${isRunning ? 'running' : 'stopped'}`} />
          <span className="text-xs text-muted" style={{ fontWeight: 600 }}>
            {isRunning ? 'Live feed active' : 'Camera inactive'}
          </span>
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
            className={`neu-btn neu-btn-sm${!useStream ? ' neu-btn-primary' : ''}`}
            onClick={() => setUseStream(false)}
            style={{ padding: '5px 10px', fontSize: '0.68rem' }}
            title="OpenCV annotated feed with detection boxes"
          >
            WS Annotated
          </button>
          <button
            className={`neu-btn neu-btn-sm${useStream ? ' neu-btn-primary' : ''}`}
            onClick={() => { setUseStream(true); setImgError(false); setMjpegKey(k => k + 1) }}
            style={{ padding: '5px 10px', fontSize: '0.68rem' }}
            title="Raw MJPEG stream from phone camera"
          >
            MJPEG Stream
          </button>
        </div>
      </div>

      {/* Viewport */}
      <div className="camera-view" style={{ borderRadius: 'var(--r-lg)' }}>

        {/* WS Annotated — OpenCV frame with detection boxes */}
        {!useStream && isRunning && frame && (
          <img
            src={frame}
            alt="Annotated feed"
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
          />
        )}

        {/* WS Annotated — waiting for first frame */}
        {!useStream && isRunning && !frame && (
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
        {useStream && isRunning && !imgError && (
          <img
            key={mjpegKey}
            src={`${api.streamUrl()}?t=${mjpegKey}`}
            alt="MJPEG stream"
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            onError={() => setImgError(true)}
          />
        )}

        {/* MJPEG error */}
        {useStream && isRunning && imgError && (
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
        {!isRunning && (
          <div className="camera-offline">
            <span style={{ fontSize: 52, opacity: 0.2 }}>📷</span>
            <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)', textAlign: 'center', padding: '0 16px' }}>
              Camera inactive — click <strong style={{ color: 'var(--success)' }}>▶ Start</strong> in the top navbar
            </span>
          </div>
        )}

        {/* Overlays — only when running */}
        {isRunning && (
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
                borderColor: 'rgba(59,130,246,0.6)', ...s,
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
              color: useStream ? '#f59e0b' : '#3b82f6',
            }}>
              {useStream ? 'MJPEG' : 'WS'}
            </div>

            {/* Last bean HUD */}
            {lastBean && (
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
                  }}>{lastBean.grade}</div>
                  <span style={{ fontSize: '0.64rem', color: 'rgba(255,255,255,0.75)', fontFamily: 'monospace' }}>
                    {lastBean.confidence?.toFixed(0)}% conf
                  </span>
                </div>
                <div style={{ display: 'flex', gap: 12 }}>
                  {lastBean.size_mm != null && (
                    <span style={{ fontSize: '0.62rem', color: 'rgba(255,255,255,0.6)', fontFamily: 'monospace' }}>
                      Ø {lastBean.size_mm?.toFixed(1)} mm
                    </span>
                  )}
                  {lastBean.recommended_bin && (
                    <span style={{ fontSize: '0.62rem', color: gradeColor, fontFamily: 'monospace', fontWeight: 700 }}>
                      → Bin {lastBean.recommended_bin.replace('grade', '')}
                    </span>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      <style>{`@keyframes cam-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}
