/**
 * useWebSocket — manages WebSocket connection to FastAPI backend.
 * Reconnects automatically on disconnect with exponential back-off.
 *
 * Returns:
 *   stats      — latest SystemStats payload
 *   lastBean   — most recently detected bean
 *   alerts     — array of Alert objects (newest first)
 *   frame      — latest annotated camera frame as base64 data URL
 *   connected  — boolean
 */

import { useState, useEffect, useRef, useCallback } from 'react'

const WS_URL = (() => {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host  = import.meta.env.VITE_WS_URL || `${proto}://${window.location.host}/ws`
  return host
})()

const INITIAL_STATS = {
  status: 'stopped',
  uptime_seconds: 0,
  beans_processed: 0,
  beans_per_minute: 0,
  good_yield_pct: 0,
  defect_rate_pct: 0,
  sort_counts: { grade1: 0, grade2: 0, grade3: 0, grade4: 0 },
  last_bean: null,
  air_pressure_mpa: 0,
  conveyor_rpm: 0,
  camera_fps: 0,
  cpu_temp_c: 0,
  active_alerts: 0,
  valve_fires: {},
  conveyor_on: false,
  compressor_on: false,
}

export function useWebSocket() {
  const [stats,     setStats]     = useState(INITIAL_STATS)
  const [lastBean,  setLastBean]  = useState(null)
  const [alerts,    setAlerts]    = useState([])
  const [frame,     setFrame]     = useState(null)
  const [connected, setConnected] = useState(false)

  const wsRef     = useRef(null)
  const retryRef  = useRef(null)
  const retryMs   = useRef(1000)
  const mountedRef= useRef(true)

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    try {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        if (!mountedRef.current) return
        setConnected(true)
        retryMs.current = 1000
        // Keep-alive ping every 20 seconds
        const ping = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping')
        }, 20000)
        ws._ping = ping
      }

      ws.onmessage = (event) => {
        if (!mountedRef.current) return
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'stats') {
            setStats(prev => ({ ...prev, ...msg.payload }))
          } else if (msg.type === 'bean') {
            setLastBean(msg.payload)
          } else if (msg.type === 'alert') {
            setAlerts(prev => [msg.payload, ...prev].slice(0, 100))
          } else if (msg.type === 'frame') {
            setFrame(`data:image/jpeg;base64,${msg.payload.data}`)
          }
        } catch (_) {}
      }

      ws.onerror = () => {
        // onclose will fire next and handle reconnect
      }

      ws.onclose = () => {
        if (ws._ping) clearInterval(ws._ping)
        if (!mountedRef.current) return
        setConnected(false)
        // Exponential back-off: 1s → 2s → 4s → 8s → max 15s
        retryRef.current = setTimeout(() => {
          retryMs.current = Math.min(retryMs.current * 2, 15000)
          connect()
        }, retryMs.current)
      }
    } catch (err) {
      console.error('WS connect error', err)
      retryRef.current = setTimeout(connect, retryMs.current)
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()
    return () => {
      mountedRef.current = false
      clearTimeout(retryRef.current)
      if (wsRef.current) wsRef.current.close()
    }
  }, [connect])

  // Expose a way to inject alerts resolved locally
  const resolveAlert = useCallback((id) => {
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, resolved: true } : a))
  }, [])

  const resolveAllAlerts = useCallback(() => {
    setAlerts(prev => prev.map(a => ({ ...a, resolved: true })))
  }, [])

  return { stats, lastBean, alerts, frame, connected, resolveAlert, resolveAllAlerts }
}
