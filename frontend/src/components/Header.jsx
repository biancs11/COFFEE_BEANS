import { useState, useEffect } from 'react'
import { api } from '../services/api'

const PAGE_TITLES = {
  '/overview':   ['Overview',   'Coffee Bean Sorting System — Live Monitor'],
  '/detection':  ['Detection',  'Feature 1 — Bean Detection & Image Acquisition'],
  '/assessment': ['Assessment', 'Feature 2 — AI-Powered Quality Assessment'],
  '/sorting':    ['Sorting',    'Feature 3 — Automated Sorting & Ejection'],
  '/errors':     ['Alerts',     'Feature 4 — Sorting Error Monitoring'],
  '/dashboard':  ['Dashboard',  'Feature 5 — Quality Monitoring & Decision Support'],
  '/settings':   ['Settings',   'System Configuration'],
}

export default function Header({ pathname, status, onToast }) {
  const [clock,   setClock]   = useState('')
  const [loading, setLoading] = useState(false)   // prevents double-click

  useEffect(() => {
    const tick = () => {
      const now = new Date()
      const pad = n => String(n).padStart(2, '0')
      setClock(`${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`)
    }
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  const [title, sub] = PAGE_TITLES[pathname] || ['System', 'Coffee Bean Sorting System']

  const handleStart = async () => {
    if (loading) return
    setLoading(true)
    try {
      const res = await api.sendCommand('start')
      if (res?.status === 'already running') {
        onToast?.('System is already running', 'info')
      } else {
        onToast?.('System started — camera, conveyor & compressor online', 'success')
      }
    } catch (e) {
      onToast?.(`Start failed: ${e.message}`, 'danger')
    } finally {
      setLoading(false)
    }
  }

  const handleStop = async () => {
    if (loading) return
    setLoading(true)
    try {
      const res = await api.sendCommand('stop')
      if (res?.status === 'already stopped') {
        onToast?.('System is already stopped', 'info')
      } else {
        onToast?.('System stopped', 'warning')
      }
    } catch (e) {
      onToast?.(`Stop failed: ${e.message}`, 'danger')
    } finally {
      setLoading(false)
    }
  }

  const handleEmergency = async () => {
    if (!confirm('EMERGENCY STOP — de-energise all outputs immediately?')) return
    if (loading) return
    setLoading(true)
    try {
      await api.sendCommand('emergency_stop')
      onToast?.('EMERGENCY STOP triggered', 'danger')
    } catch (e) {
      onToast?.(`Emergency stop failed: ${e.message}`, 'danger')
    } finally {
      setLoading(false)
    }
  }

  const isRunning = status === 'running'
  const isError   = status === 'error'

  return (
    <header className="header">
      <div>
        <div className="header-title">{title}</div>
        <div className="header-sub">{sub}</div>
      </div>

      <div className="header-right">
        {/* Status indicator */}
        <div className="flex items-center gap-2">
          <span className={`status-dot ${isError ? 'error' : status}`} />
          <span className="text-xs text-muted font-mono" style={{ textTransform: 'uppercase' }}>
            {loading ? 'working…' : status}
          </span>
        </div>

        <div className="clock">{clock}</div>

        {/* Start / Stop button — mutually exclusive, shows loading spinner */}
        {!isRunning ? (
          <button
            className="neu-btn neu-btn-success"
            onClick={handleStart}
            disabled={loading}
            style={{ opacity: loading ? 0.6 : 1, minWidth: 88 }}
          >
            {loading ? '⏳' : '▶'} {loading ? 'Starting…' : 'Start'}
          </button>
        ) : (
          <button
            className="neu-btn neu-btn-warning"
            onClick={handleStop}
            disabled={loading}
            style={{ opacity: loading ? 0.6 : 1, minWidth: 88 }}
          >
            {loading ? '⏳' : '⏹'} {loading ? 'Stopping…' : 'Stop'}
          </button>
        )}

        {/* Emergency stop — always visible */}
        <button
          className="neu-btn neu-btn-danger"
          style={{ fontSize: '0.72rem', opacity: loading ? 0.6 : 1 }}
          onClick={handleEmergency}
          disabled={loading}
        >
          🛑 E-Stop
        </button>
      </div>
    </header>
  )
}
