import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../services/api'
import CoffeeBeanLogo from './CoffeeBeanLogo'

function pad(n) { return String(n).padStart(2, '0') }

function formatDate(d) {
  return d.toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
  })
}

export default function Navbar({ status, onToast, theme, onToggleTheme, currentPath, adminUser, onAdminLogout }) {
  const navigate = useNavigate()
  const isAdmin  = currentPath === '/admin'
  const [time,             setTime]             = useState('')
  const [date,             setDate]             = useState('')
  const [loading,          setLoading]          = useState(false)
  const [optimisticStatus, setOptimisticStatus] = useState(null)
  const optimisticTimer = useRef(null)

  // Clear optimistic once real WS status catches up.
  // Only clear when the real status matches — never auto-revert to a previous state.
  useEffect(() => {
    if (optimisticStatus === null) return
    const matches =
      (optimisticStatus === 'running' && status === 'running') ||
      (optimisticStatus === 'stopped' && status === 'stopped') ||
      (optimisticStatus === 'paused'  && status === 'paused')
    if (matches) setOptimisticStatus(null)
  }, [status, optimisticStatus])

  const setOptimistic = (s) => {
    clearTimeout(optimisticTimer.current)
    setOptimisticStatus(s)
    // No auto-clear timeout — keep optimistic until WS confirms or error
  }

  // Live clock
  useEffect(() => {
    const tick = () => {
      const now = new Date()
      setTime(`${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`)
      setDate(formatDate(now))
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  const sendCmd = useCallback(async (command, optimistic, successMsg, warningMsg) => {
    if (loading) return
    setLoading(true)
    setOptimistic(optimistic)
    try {
      const res = await api.sendCommand(command)
      const already = res?.status?.startsWith('already')
      onToast?.(already ? `System is already ${optimistic}` : successMsg,
                already ? 'info' : (command === 'stop' ? 'warning' : 'success'))
    } catch (e) {
      setOptimistic(null)
      onToast?.(`${command} failed: ${e.message}`, 'danger')
    } finally {
      setLoading(false)
    }
  }, [loading, onToast])

  const handleStart = () => {
    // If paused, resume instead of starting a new session
    if (displayStatus === 'paused') {
      sendCmd('resume', 'running', 'System resumed — detection active')
    } else {
      sendCmd('start', 'running', 'System started — camera & detection online')
    }
  }
  const handleStop  = () => sendCmd('stop',  'stopped', 'System stopped')
  const handlePause = () => sendCmd('pause', 'paused',  'System paused — camera still active')

  const displayStatus  = optimisticStatus ?? status
  const isRunning      = displayStatus === 'running'
  const isPaused       = displayStatus === 'paused'
  const isStopped      = !isRunning && !isPaused
  const isError        = displayStatus === 'error'
  const isDark         = theme === 'dark'
  const statusDotClass = isError ? 'error' : (displayStatus || 'stopped')

  return (
    <header className="navbar">

      {/* ── LEFT: Logo ── */}
      <div className="navbar-logo">
        <div className="navbar-logo-icon">
          <CoffeeBeanLogo size={26} color="#d4a76a" />
        </div>
        <div className="navbar-logo-text">
          <span className="navbar-logo-title">CoffeeSort</span>
          <span className="navbar-logo-sub">AI SORTING SYSTEM</span>
        </div>
      </div>

      {/* ── CENTRE: View switcher ── */}
      <div className="navbar-view-switcher">
        <button
          className={`navbar-view-btn${!isAdmin ? ' active' : ''}`}
          onClick={() => navigate('/dashboard')}
        >
          📷 Operator
        </button>
        <button
          className={`navbar-view-btn${isAdmin ? ' active' : ''}`}
          onClick={() => navigate('/admin')}
        >
          📊 Admin
        </button>
      </div>

      {/* ── RIGHT: controls ── */}
      <div className="navbar-right">

        {/* Status pill — hidden on Admin Dashboard */}
        {!isAdmin && (
          <div className="status-pill">
            <span className={`status-dot ${statusDotClass}`} />
            <span style={{ textTransform: 'uppercase', fontSize: '0.68rem', fontWeight: 700, letterSpacing: '0.06em' }}>
              {loading ? 'Working…' : (displayStatus || 'stopped')}
            </span>
          </div>
        )}

        {/* ── 3 persistent buttons — hidden on Admin Dashboard ── */}
        {!isAdmin && (
          <>
            {/* START — only lit when system is fully stopped */}
            <button
              className="navbar-ctrl-btn"
              data-active={isStopped ? 'true' : undefined}
              data-variant="success"
              onClick={handleStart}
              title="Start system"
            >
              <span className="navbar-ctrl-icon">▶</span>
              <span className="navbar-ctrl-label">Start</span>
            </button>

            {/* PAUSE — lit when running OR paused */}
            <button
              className="navbar-ctrl-btn"
              data-active={isRunning || isPaused ? 'true' : undefined}
              data-variant="warning"
              onClick={handlePause}
              title="Pause system"
            >
              <span className="navbar-ctrl-icon">⏸</span>
              <span className="navbar-ctrl-label">Pause</span>
            </button>

            {/* STOP — lit when running OR paused */}
            <button
              className="navbar-ctrl-btn"
              data-active={isRunning || isPaused ? 'true' : undefined}
              data-variant="danger"
              onClick={handleStop}
              title="Stop system"
            >
              <span className="navbar-ctrl-icon">⏹</span>
              <span className="navbar-ctrl-label">Stop</span>
            </button>
          </>
        )}

        {/* Separator */}
        <div style={{ width: 1, height: 28, background: 'var(--border)', margin: '0 2px' }} />

        {/* Date & time */}
        <div className="navbar-datetime">
          <span className="navbar-time">{time}</span>
          <span className="navbar-date">{date}</span>
        </div>

        {/* Theme toggle */}
        <button
          className="theme-toggle-btn"
          onClick={onToggleTheme}
          title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
          aria-label="Toggle theme"
        >
          {isDark ? '☀️' : '🌙'}
        </button>

        {/* Admin user badge + logout — shown only when on admin page and logged in */}
        {isAdmin && adminUser && (
          <>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'rgba(16,185,129,0.1)',
              border: '1px solid rgba(16,185,129,0.2)',
              borderRadius: 'var(--r-full)',
              padding: '4px 10px',
              fontSize: '0.68rem', fontWeight: 600,
              color: 'var(--success)',
            }}>
              👤 {adminUser}
            </div>
            <button
              className="neu-btn neu-btn-sm"
              onClick={onAdminLogout}
              style={{ fontSize: '0.68rem' }}
              title="Sign out of Admin Dashboard"
            >
              🔓 Sign Out
            </button>
          </>
        )}

      </div>
    </header>
  )
}
