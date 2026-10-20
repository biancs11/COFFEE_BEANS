/**
 * Training page — upload example images per grade, trigger re-training,
 * monitor detector mode (ML vs HSV-fallback), manage training image library.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../services/api'

// ── Grade config ──────────────────────────────────────────────
const GRADES = [
  {
    key:   'grade1',
    label: 'Grade 1 — Premium',
    desc:  'Pale cream-tan. Uniform colour, no defects, well-formed oval.',
    color: 'var(--premium)',
    icon:  '🟢',
    bg:    'rgba(16,185,129,0.08)',
    border:'rgba(16,185,129,0.25)',
  },
  {
    key:   'grade2',
    label: 'Grade 2 — Good',
    desc:  'Warm golden-tan. Slight variation acceptable, minor blemishes ok.',
    color: 'var(--grade1)',
    icon:  '🔵',
    bg:    'rgba(59,130,246,0.08)',
    border:'rgba(59,130,246,0.25)',
  },
  {
    key:   'grade3',
    label: 'Grade 3 — Average',
    desc:  'Olive / yellow-green. Noticeable colour irregularities or mild surface marks.',
    color: 'var(--grade2)',
    icon:  '🟡',
    bg:    'rgba(245,158,11,0.08)',
    border:'rgba(245,158,11,0.25)',
  },
  {
    key:   'grade4',
    label: 'Grade 4 — Defect',
    desc:  'Burnt, mouldy, pale/washed-out, or broken beans.',
    color: 'var(--defective)',
    icon:  '🔴',
    bg:    'rgba(239,68,68,0.08)',
    border:'rgba(239,68,68,0.25)',
  },
]

// ── Small reusable components ─────────────────────────────────

function StatusBadge({ trained }) {
  return (
    <span style={{
      display:      'inline-flex',
      alignItems:   'center',
      gap:          5,
      padding:      '4px 12px',
      borderRadius: 'var(--r-full)',
      fontSize:     '0.72rem',
      fontWeight:   700,
      letterSpacing:'0.05em',
      background:   trained ? 'rgba(16,185,129,0.12)' : 'rgba(245,158,11,0.12)',
      color:        trained ? 'var(--success)'         : 'var(--warning)',
      border:       trained ? '1px solid rgba(16,185,129,0.3)' : '1px solid rgba(245,158,11,0.3)',
    }}>
      {trained ? '✓ ML Mode Active' : '⚠ HSV Fallback Mode'}
    </span>
  )
}

function SampleCount({ n, color }) {
  return (
    <span className="font-mono" style={{
      fontSize:   '0.7rem',
      fontWeight: 700,
      color,
      background: color + '18',
      border:     `1px solid ${color}33`,
      borderRadius: 'var(--r-full)',
      padding:    '2px 8px',
    }}>
      {n} sample{n !== 1 ? 's' : ''}
    </span>
  )
}

function ProgressBar({ value, max, color }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0
  return (
    <div className="neu-progress-track" style={{ height: 5, marginTop: 4 }}>
      <div style={{
        height: '100%', width: `${pct}%`,
        background: color, borderRadius: 'inherit',
        transition: 'width 0.4s ease',
      }} />
    </div>
  )
}

// ── Drop zone for one grade ───────────────────────────────────

function GradeUploadZone({ grade, sampleCount, imageMeta, onUpload, onClear, onDeleteOne, uploading }) {
  const inputRef  = useRef(null)
  const [dragOver, setDragOver] = useState(false)

  const handleFiles = useCallback(async (files) => {
    if (!files || files.length === 0) return
    const accepted = [...files].filter(f => f.type.startsWith('image/'))
    if (accepted.length === 0) return
    for (const file of accepted) {
      await onUpload(grade.key, file)
    }
  }, [grade.key, onUpload])

  const onDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    handleFiles(e.dataTransfer.files)
  }

  return (
    <div style={{
      border:       `1.5px solid ${dragOver ? grade.color : grade.border}`,
      borderRadius: 'var(--r-md)',
      background:   dragOver ? grade.bg : 'var(--bg-raised)',
      padding:      16,
      transition:   'all 0.2s',
      boxShadow:    dragOver ? `0 0 0 3px ${grade.color}22` : 'var(--shadow-sm)',
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 16 }}>{grade.icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '0.8rem', fontWeight: 700, color: grade.color }}>
            {grade.label}
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginTop: 1 }}>
            {grade.desc}
          </div>
        </div>
        <SampleCount n={sampleCount} color={grade.color} />
      </div>

      <ProgressBar value={sampleCount} max={50} color={grade.color} />

      {/* Drop area */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        style={{
          marginTop:    10,
          border:       `1.5px dashed ${dragOver ? grade.color : 'var(--border)'}`,
          borderRadius: 'var(--r-sm)',
          padding:      '12px 8px',
          textAlign:    'center',
          cursor:       uploading ? 'wait' : 'pointer',
          opacity:      uploading ? 0.6 : 1,
          transition:   'all 0.2s',
          background:   dragOver ? grade.bg : 'transparent',
        }}
      >
        <div style={{ fontSize: 20, marginBottom: 4 }}>
          {uploading ? '⏳' : '📁'}
        </div>
        <div style={{ fontSize: '0.72rem', color: 'var(--text-secondary)', fontWeight: 500 }}>
          {uploading ? 'Uploading…' : 'Drop images here or click to browse'}
        </div>
        <div style={{ fontSize: '0.64rem', color: 'var(--text-muted)', marginTop: 3 }}>
          JPEG · PNG · WebP — multiple files OK
        </div>
        <input
          ref={inputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,image/bmp"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {/* Image list */}
      {imageMeta && imageMeta.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            marginBottom: 6,
          }}>
            <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', fontWeight: 600 }}>
              UPLOADED FILES
            </span>
            <button
              className="neu-btn neu-btn-sm"
              style={{ fontSize: '0.62rem', color: 'var(--danger)', padding: '2px 8px' }}
              onClick={() => onClear(grade.key)}
              title={`Remove all ${grade.label} images`}
            >
              🗑 Clear all
            </button>
          </div>
          <div style={{
            maxHeight: 110,
            overflowY: 'auto',
            display:   'flex',
            flexDirection: 'column',
            gap: 3,
          }}>
            {imageMeta.map(img => (
              <div key={img.filename} style={{
                display:      'flex',
                alignItems:   'center',
                gap:          6,
                background:   'var(--bg-deep)',
                borderRadius: 'var(--r-sm)',
                padding:      '4px 8px',
                fontSize:     '0.68rem',
              }}>
                <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>🖼</span>
                <span style={{ flex: 1, color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {img.filename}
                </span>
                <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>
                  {(img.size_bytes / 1024).toFixed(0)} KB
                </span>
                <button
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--danger)', fontSize: 12, padding: '0 2px',
                    lineHeight: 1, flexShrink: 0,
                  }}
                  title="Delete this image"
                  onClick={() => onDeleteOne(grade.key, img.filename)}
                >
                  ✕
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main Training page ────────────────────────────────────────

export default function Training({ onToast }) {
  const [status,     setStatus]     = useState(null)
  const [images,     setImages]     = useState({})
  const [loading,    setLoading]    = useState(true)
  const [training,   setTraining]   = useState(false)
  const [uploading,  setUploading]  = useState({})   // { grade_key: bool }
  const [trainLog,   setTrainLog]   = useState(null)

  // ── Fetch status + image list ──────────────────────────────
  const refresh = useCallback(async () => {
    try {
      const [st, imgs] = await Promise.all([
        api.getTrainingStatus(),
        api.getTrainingImages(),
      ])
      setStatus(st)
      setImages(imgs)
    } catch (e) {
      onToast?.(`Could not load training status: ${e.message}`, 'danger')
    } finally {
      setLoading(false)
    }
  }, [onToast])

  useEffect(() => { refresh() }, [refresh])

  // ── Upload handler ─────────────────────────────────────────
  const handleUpload = useCallback(async (gradeKey, file) => {
    setUploading(prev => ({ ...prev, [gradeKey]: true }))
    try {
      await api.uploadTrainingImage(gradeKey, file)
      onToast?.(`Uploaded ${file.name} → ${gradeKey}`, 'success')
      await refresh()
    } catch (e) {
      onToast?.(`Upload failed: ${e.message}`, 'danger')
    } finally {
      setUploading(prev => ({ ...prev, [gradeKey]: false }))
    }
  }, [onToast, refresh])

  // ── Delete one image ───────────────────────────────────────
  const handleDeleteOne = useCallback(async (gradeKey, filename) => {
    try {
      await api.deleteTrainingImage(gradeKey, filename)
      onToast?.(`Deleted ${filename}`, 'info')
      await refresh()
    } catch (e) {
      onToast?.(`Delete failed: ${e.message}`, 'danger')
    }
  }, [onToast, refresh])

  // ── Clear all images for a grade ─────────────────────────
  const handleClear = useCallback(async (gradeKey) => {
    try {
      const res = await api.clearGradeImages(gradeKey)
      onToast?.(`Cleared ${res.deleted} image${res.deleted !== 1 ? 's' : ''} from ${gradeKey}`, 'warning')
      await refresh()
    } catch (e) {
      onToast?.(`Clear failed: ${e.message}`, 'danger')
    }
  }, [onToast, refresh])

  // ── Train ─────────────────────────────────────────────────
  const handleTrain = useCallback(async () => {
    setTraining(true)
    setTrainLog(null)
    try {
      const res = await api.runTraining()
      setTrainLog(res)
      onToast?.(res.message, 'success')
      await refresh()
    } catch (e) {
      setTrainLog({ ok: false, message: e.message })
      onToast?.(`Training failed: ${e.message}`, 'danger')
    } finally {
      setTraining(false)
    }
  }, [onToast, refresh])

  // ── Reset profiles ────────────────────────────────────────
  const handleReset = useCallback(async () => {
    if (!confirm('Reset ML profiles? The detector will fall back to HSV mode until re-trained.')) return
    try {
      await api.resetProfiles()
      setTrainLog(null)
      onToast?.('Profiles reset — detector reverted to HSV-fallback mode', 'warning')
      await refresh()
    } catch (e) {
      onToast?.(`Reset failed: ${e.message}`, 'danger')
    }
  }, [onToast, refresh])

  // ── Derived counts ────────────────────────────────────────
  const sampleCounts  = status?.grade_stats  || {}
  const imageCounts   = status?.image_counts || {}
  const totalImages   = Object.values(imageCounts).reduce((a, b) => a + b, 0)
  const totalSamples  = Object.values(sampleCounts).reduce((a, n) => a + (n?.n ?? n ?? 0), 0)
  const isTrained     = status?.trained ?? false
  const mode          = status?.mode    ?? '—'

  // Minimum images needed per grade to enable train button
  const gradesWithImages = GRADES.filter(g => (imageCounts[g.key] || 0) > 0).length
  const canTrain = gradesWithImages >= 2

  if (loading) {
    return (
      <div className="page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '50vh' }}>
        <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
          <div style={{ fontSize: 28, marginBottom: 10 }}>⚙️</div>
          Loading training status…
        </div>
      </div>
    )
  }

  return (
    <div className="page">

      {/* ── Page header ── */}
      <div className="page-header">
        <h2>🧠 Detector Training — Appearance-Based Grading</h2>
        <p>
          Upload example bean images per grade to teach the detector how each grade looks.
          The detector extracts 16 visual features (colour, texture, shape) and builds a
          per-grade appearance profile. Once trained, grading uses learned appearance
          rather than fixed colour thresholds, making it accurate across lighting conditions.
        </p>
      </div>

      {/* ── Status row ── */}
      <div className="grid-4 mb-4">
        {[
          {
            icon:  '🤖',
            val:   mode,
            label: 'Detector Mode',
            v:     isTrained ? 'grade1' : 'coffee',
          },
          {
            icon:  '🖼',
            val:   totalImages,
            label: 'Training Images',
            v:     'premium',
          },
          {
            icon:  '🔬',
            val:   totalSamples,
            label: 'Feature Samples',
            v:     'grade2',
          },
          {
            icon:  '📊',
            val:   `${gradesWithImages} / 4`,
            label: 'Grades Covered',
            v:     'grade3',
          },
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

      {/* ── Detector status banner ── */}
      <div className="neu-card mb-4" style={{
        display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
        padding: '14px 20px',
      }}>
        <StatusBadge trained={isTrained} />

        <div style={{ flex: 1, minWidth: 200 }}>
          {isTrained ? (
            <div style={{ fontSize: '0.76rem', color: 'var(--text-secondary)' }}>
              Grading uses learned appearance profiles.
              {' '}
              <strong style={{ color: 'var(--text-primary)' }}>
                {Object.entries(sampleCounts)
                  .filter(([, v]) => (v?.n ?? v ?? 0) > 0)
                  .map(([k, v]) => `${k}: ${v?.n ?? v}`)
                  .join(' · ')}
              </strong>
            </div>
          ) : (
            <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)' }}>
              Upload images for at least 2 grades then click <strong>Train Now</strong> to enable ML mode.
              The HSV-fallback grader remains active until training completes.
            </div>
          )}
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="neu-btn"
            onClick={handleTrain}
            disabled={training || !canTrain}
            style={{
              background:   canTrain ? 'rgba(16,185,129,0.12)' : undefined,
              color:        canTrain ? 'var(--success)'        : undefined,
              border:       canTrain ? '1px solid rgba(16,185,129,0.3)' : undefined,
              fontWeight:   700,
              fontSize:     '0.78rem',
              opacity:      (!canTrain || training) ? 0.5 : 1,
              cursor:       (!canTrain || training) ? 'not-allowed' : 'pointer',
            }}
            title={!canTrain ? 'Upload images for at least 2 grades first' : 'Run training now'}
          >
            {training ? '⏳ Training…' : '▶ Train Now'}
          </button>

          {isTrained && (
            <button
              className="neu-btn neu-btn-sm"
              onClick={handleReset}
              style={{ color: 'var(--danger)', fontSize: '0.72rem' }}
              title="Delete saved profiles and revert to HSV mode"
            >
              🗑 Reset
            </button>
          )}

          <button
            className="neu-btn neu-btn-sm"
            onClick={refresh}
            style={{ fontSize: '0.72rem' }}
            title="Refresh status"
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* ── Training result log ── */}
      {trainLog && (
        <div className="neu-card mb-4" style={{
          padding: '12px 16px',
          border:  `1px solid ${trainLog.ok ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`,
          background: trainLog.ok ? 'rgba(16,185,129,0.04)' : 'rgba(239,68,68,0.04)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{ fontSize: 16 }}>{trainLog.ok ? '✅' : '❌'}</span>
            <span style={{
              fontSize: '0.78rem', fontWeight: 700,
              color: trainLog.ok ? 'var(--success)' : 'var(--danger)',
            }}>
              {trainLog.message}
            </span>
          </div>

          {trainLog.stats && (
            <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              {GRADES.map(g => (
                <div key={g.key} style={{ fontSize: '0.7rem' }}>
                  <span style={{ color: g.color, fontWeight: 700 }}>{g.label.split('—')[0].trim()}</span>
                  <span style={{ color: 'var(--text-muted)' }}>: {trainLog.stats[g.key] ?? 0} samples</span>
                </div>
              ))}
            </div>
          )}

          {trainLog.errors && trainLog.errors.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontSize: '0.68rem', color: 'var(--warning)', fontWeight: 600, marginBottom: 4 }}>
                WARNINGS ({trainLog.errors.length})
              </div>
              <div style={{
                maxHeight: 72, overflowY: 'auto',
                fontSize: '0.65rem', color: 'var(--text-muted)',
                fontFamily: 'var(--font-mono)',
              }}>
                {trainLog.errors.map((e, i) => <div key={i}>{e}</div>)}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Upload zones grid ── */}
      <div style={{
        display:             'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
        gap:                 16,
        marginBottom:        24,
      }}>
        {GRADES.map(grade => (
          <GradeUploadZone
            key={grade.key}
            grade={grade}
            sampleCount={sampleCounts[grade.key]?.n ?? sampleCounts[grade.key] ?? 0}
            imageMeta={images[grade.key] || []}
            onUpload={handleUpload}
            onClear={handleClear}
            onDeleteOne={handleDeleteOne}
            uploading={uploading[grade.key] || false}
          />
        ))}
      </div>

      {/* ── How-it-works section ── */}
      <div className="neu-card">
        <div className="section-label mb-3">How Appearance-Based Grading Works</div>
        <div style={{
          display:             'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
          gap:                 12,
        }}>
          {[
            {
              step: '1',
              icon: '🌅',
              title: 'Lighting Normalisation',
              body:  'Gray-world white balance is applied to every frame so colour readings stay stable under different lighting temperatures and intensities.',
            },
            {
              step: '2',
              icon: '🔍',
              title: 'Bean Gate (5-check filter)',
              body:  'Each detected blob must pass ≥ 4 of 5 checks — circularity, solidity, aspect ratio, physical size, and surface texture — before it can be graded. Non-bean objects are rejected here.',
            },
            {
              step: '3',
              icon: '📐',
              title: '16-Dim Feature Extraction',
              body:  'Mean & std of H/S/V, 8-bin hue histogram, Laplacian texture roughness, and shape aspect ratio are extracted per bean ROI.',
            },
            {
              step: '4',
              icon: '🧬',
              title: 'Nearest-Centroid Grading',
              body:  'Each bean\'s feature vector is compared to the per-grade centroids learned from your example images using normalised Euclidean (z-score) distance. Closest grade wins.',
            },
            {
              step: '5',
              icon: '⚡',
              title: 'HSV Fallback',
              body:  'If no profiles exist the detector falls back to refined HSV-band lookup — still shadow-resistant and bean-only — so the system always works out of the box.',
            },
          ].map(({ step, icon, title, body }) => (
            <div key={step} className="neu-inset" style={{ padding: '12px 14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                <span style={{
                  width: 22, height: 22, borderRadius: '50%',
                  background: 'var(--coffee-cream)', color: '#3d2b1f',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '0.65rem', fontWeight: 800, flexShrink: 0,
                }}>
                  {step}
                </span>
                <span style={{ fontSize: 14 }}>{icon}</span>
                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                  {title}
                </span>
              </div>
              <p style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.5 }}>
                {body}
              </p>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}
