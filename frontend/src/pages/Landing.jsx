import { useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import CoffeeBeanLogo from '../components/CoffeeBeanLogo'

export default function Landing() {
  const navigate            = useNavigate()
  const [ready, setReady]   = useState(false)
  const [serverOk, setServerOk] = useState(null)  // null=checking, true=ok, false=offline

  // Fade in on mount
  useEffect(() => {
    const t = setTimeout(() => setReady(true), 80)
    return () => clearTimeout(t)
  }, [])

  // Check if backend is reachable
  useEffect(() => {
    let cancelled = false
    async function check() {
      try {
        const res = await fetch('/health', { cache: 'no-store', signal: AbortSignal.timeout(3000) })
        if (!cancelled) setServerOk(res.ok || res.status === 503)
      } catch (_) {
        if (!cancelled) setServerOk(false)
      }
    }
    check()
    const interval = setInterval(check, 3000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  const goToDashboard = (e) => {
    e.stopPropagation()
    navigate('/dashboard')
  }

  return (
    <div
      style={{
        position: 'fixed', inset: 0,
        overflow: 'hidden',
        fontFamily: "'Inter', sans-serif",
        userSelect: 'none',
        background: `
          radial-gradient(ellipse 80% 60% at 20% 50%, rgba(111,78,55,0.45) 0%, transparent 60%),
          radial-gradient(ellipse 60% 80% at 80% 30%, rgba(61,43,31,0.6) 0%, transparent 55%),
          radial-gradient(ellipse 50% 50% at 50% 80%, rgba(30,20,10,0.5) 0%, transparent 60%),
          linear-gradient(145deg, #0f0a06 0%, #1a1008 25%, #221510 50%, #18100a 75%, #0c0806 100%)
        `,
        opacity: ready ? 1 : 0,
        transition: 'opacity 0.6s ease',
      }}
    >
      {/* Noise texture */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E")`,
        opacity: 0.4,
      }} />

      {/* Warm glow */}
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        background: `
          radial-gradient(circle 600px at 15% 60%, rgba(160,120,80,0.08) 0%, transparent 70%),
          radial-gradient(circle 400px at 85% 20%, rgba(120,80,50,0.06) 0%, transparent 70%)
        `,
      }} />

      {/* Logo top-left */}
      <div style={{
        position: 'absolute', top: 32, left: 36,
        display: 'flex', alignItems: 'center', gap: 14,
        zIndex: 10,
      }}>
        <div style={{
          width: 44, height: 44,
          background: 'linear-gradient(135deg, #6f4e37, #a0785a)',
          borderRadius: 10,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 4px 20px rgba(111,78,55,0.5)',
        }}>
          <CoffeeBeanLogo size={28} color="#ffe0a0" />
        </div>
        <div>
          <div style={{ fontSize: '0.88rem', fontWeight: 700, color: 'rgba(255,255,255,0.92)', letterSpacing: '0.02em' }}>CoffeeSort</div>
          <div style={{ fontSize: '0.62rem', fontWeight: 500, color: 'rgba(255,255,255,0.38)', letterSpacing: '0.12em', textTransform: 'uppercase', marginTop: 1 }}>AI Sorting System</div>
        </div>
      </div>

      {/* Version badge */}
      <div style={{
        position: 'absolute', top: 36, right: 36,
        fontSize: '0.65rem', fontWeight: 600,
        color: 'rgba(212,167,106,0.5)',
        letterSpacing: '0.1em', textTransform: 'uppercase',
        zIndex: 10,
      }}>v 2.0</div>

      {/* Main content */}
      <div style={{
        position: 'absolute',
        top: '50%', left: '50%',
        transform: 'translate(-50%, -50%)',
        textAlign: 'center',
        zIndex: 20,
        width: '100%',
        maxWidth: 720,
        padding: '0 32px',
      }}>

        {/* Server status badge */}
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 8,
          background: serverOk === false
            ? 'rgba(239,68,68,0.1)' : 'rgba(212,167,106,0.08)',
          border: `1px solid ${serverOk === false
            ? 'rgba(239,68,68,0.25)' : 'rgba(212,167,106,0.18)'}`,
          borderRadius: 100,
          padding: '5px 16px',
          marginBottom: 28,
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: serverOk === null ? '#888'
              : serverOk ? '#10b981' : '#ef4444',
            boxShadow: serverOk ? '0 0 8px #10b981' : 'none',
            display: 'inline-block',
          }} />
          <span style={{
            fontSize: '0.68rem', fontWeight: 600,
            color: serverOk === false
              ? 'rgba(239,68,68,0.8)' : 'rgba(212,167,106,0.8)',
            letterSpacing: '0.12em', textTransform: 'uppercase',
          }}>
            {serverOk === null
              ? 'Connecting to server…'
              : serverOk
              ? 'System Online · Ready'
              : 'Server Offline — run start_system.sh'}
          </span>
        </div>

        {/* Main heading */}
        <h1 style={{
          margin: 0,
          fontSize: 'clamp(2.2rem, 5.5vw, 4rem)',
          fontWeight: 800,
          lineHeight: 1.15,
          letterSpacing: '-0.02em',
          color: '#fff',
        }}>
          Coffee Bean Sorting System
          <br />
          <span style={{ position: 'relative', display: 'inline-block', marginTop: 10 }}>
            <span style={{
              position: 'absolute', inset: '-8px -16px',
              background: 'radial-gradient(ellipse at center, rgba(245,200,66,0.18) 0%, rgba(212,167,106,0.12) 40%, transparent 70%)',
              borderRadius: 12,
              animation: 'glowPulse 2.5s ease-in-out infinite',
              pointerEvents: 'none',
            }} />
            <span style={{
              fontSize: 'clamp(1rem, 2.5vw, 1.6rem)',
              fontWeight: 700,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              background: 'linear-gradient(135deg, #ffe8b0 0%, #d4a76a 40%, #f5c842 70%, #a0785a 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
              filter: 'drop-shadow(0 0 18px rgba(212,167,106,0.9)) drop-shadow(0 0 40px rgba(245,200,66,0.5))',
              display: 'inline-block',
              position: 'relative',
            }}>
              Using Size and Color Detection
            </span>
          </span>
        </h1>

        <style>{`
          @keyframes glowPulse {
            0%, 100% { opacity: 0.7; transform: scale(1); }
            50%       { opacity: 1;   transform: scale(1.04); }
          }
        `}</style>

        {/* Subtitle */}
        <p style={{
          margin: '20px auto 0',
          maxWidth: 480,
          fontSize: 'clamp(0.88rem, 2vw, 1.05rem)',
          fontWeight: 400,
          color: 'rgba(255,255,255,0.45)',
          lineHeight: 1.7,
        }}>
          Automated quality grading using size and color detection.
          Sorts beans into Premium, Good, Average, and Defect categories in real time.
        </p>

        {/* Divider */}
        <div style={{
          display: 'flex', alignItems: 'center',
          justifyContent: 'center', gap: 16,
          margin: '28px auto',
          maxWidth: 260,
        }}>
          <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.08)' }} />
          <div style={{ display: 'flex', gap: 5 }}>
            {['#10b981','#3b82f6','#f59e0b','#ef4444'].map((c, i) => (
              <div key={i} style={{
                width: 8, height: 8, borderRadius: '50%',
                background: c, opacity: 0.7, boxShadow: `0 0 6px ${c}`,
              }} />
            ))}
          </div>
          <div style={{ flex: 1, height: 1, background: 'rgba(255,255,255,0.08)' }} />
        </div>

        {/* Grade pills */}
        <div style={{
          display: 'flex', justifyContent: 'center',
          gap: 10, flexWrap: 'wrap', marginBottom: 40,
        }}>
          {[
            { label: 'Grade 1', sub: 'Premium', color: '#10b981' },
            { label: 'Grade 2', sub: 'Good',    color: '#3b82f6' },
            { label: 'Grade 3', sub: 'Average', color: '#f59e0b' },
            { label: 'Grade 4', sub: 'Defect',  color: '#ef4444' },
          ].map(g => (
            <div key={g.label} style={{
              display: 'flex', alignItems: 'center', gap: 7,
              background: 'rgba(255,255,255,0.04)',
              border: `1px solid ${g.color}30`,
              borderRadius: 8, padding: '7px 14px',
            }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: g.color, flexShrink: 0 }} />
              <span style={{ fontSize: '0.72rem', fontWeight: 700, color: g.color }}>{g.label}</span>
              <span style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.35)' }}>{g.sub}</span>
            </div>
          ))}
        </div>

        {/* CTA — always visible, clear button */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
          <button
            onClick={goToDashboard}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 10,
              background: serverOk === false
                ? 'rgba(100,80,60,0.4)'
                : 'linear-gradient(135deg, #6f4e37, #a0785a)',
              color: '#fff',
              fontWeight: 700,
              fontSize: '1rem',
              letterSpacing: '0.04em',
              padding: '16px 40px',
              borderRadius: 14,
              boxShadow: '0 8px 32px rgba(111,78,55,0.45), 0 2px 8px rgba(0,0,0,0.3)',
              cursor: 'pointer',
              border: 'none',
              transition: 'transform 0.15s ease, box-shadow 0.15s ease',
            }}
            onMouseEnter={e => { e.currentTarget.style.transform = 'scale(1.04)'; e.currentTarget.style.boxShadow = '0 12px 40px rgba(111,78,55,0.6)' }}
            onMouseLeave={e => { e.currentTarget.style.transform = 'scale(1)'; e.currentTarget.style.boxShadow = '0 8px 32px rgba(111,78,55,0.45)' }}
          >
            <span>Open Dashboard</span>
            <span style={{ fontSize: '1.1rem' }}>→</span>
          </button>

          {serverOk === false && (
            <div style={{
              fontSize: '0.7rem',
              color: 'rgba(239,68,68,0.7)',
              letterSpacing: '0.04em',
            }}>
              Server offline — start it first, then click Open Dashboard
            </div>
          )}

          {serverOk !== false && (
            <div style={{
              fontSize: '0.65rem',
              color: 'rgba(255,255,255,0.2)',
              letterSpacing: '0.08em',
            }}>
              Click to continue
            </div>
          )}
        </div>

      </div>
    </div>
  )
}
