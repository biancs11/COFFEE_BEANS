/**
 * API service — REST client for the FastAPI backend.
 * Base URL is empty in production (same origin).
 * In dev, Vite proxy forwards /api → http://localhost:8000.
 */

const BASE = import.meta.env.VITE_API_URL || ''

async function request(method, path, body) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  if (body !== undefined) opts.body = JSON.stringify(body)

  const res = await fetch(`${BASE}${path}`, opts)

  if (!res.ok) {
    // Try to parse a JSON error detail from FastAPI
    let detail = `HTTP ${res.status}`
    try {
      const json = await res.json()
      detail = json.detail || JSON.stringify(json)
    } catch (_) {
      detail = await res.text().catch(() => `HTTP ${res.status}`)
    }
    throw new Error(detail)
  }

  // 204 No Content
  if (res.status === 204) return null

  return res.json()
}

export const api = {
  // ── System control ──────────────────────────────────────────
  sendCommand: (command) => request('POST', '/api/system/command', { command }),

  // ── Stats & settings ────────────────────────────────────────
  getStats:       ()         => request('GET',  '/api/stats'),
  getSettings:    ()         => request('GET',  '/api/settings'),
  updateSettings: (settings) => request('POST', '/api/settings', settings),

  // ── Data ────────────────────────────────────────────────────
  getBeans:   (limit = 50)  => request('GET', `/api/beans?limit=${limit}`),
  getAlerts:  (limit = 50)  => request('GET', `/api/alerts?limit=${limit}`),
  getSessions:(limit = 20)  => request('GET', `/api/sessions?limit=${limit}`),

  // ── Alert management ────────────────────────────────────────
  acknowledgeAlert:    (id) => request('POST', `/api/alerts/${id}/acknowledge`),
  acknowledgeAllAlerts: ()  => request('POST', '/api/alerts/acknowledge_all'),
  // Legacy aliases (React components still use these names)
  resolveAlert:    (id) => request('POST', `/api/alerts/${id}/acknowledge`),
  resolveAllAlerts: ()  => request('POST', '/api/alerts/acknowledge_all'),

  // ── Analytics ────────────────────────────────────────────────
  getAllTimeSummary: ()    => request('GET', '/api/analytics/summary'),
  getSessionSummary:(id)  => request('GET', `/api/analytics/session/${id}`),

  // ── Calibration ──────────────────────────────────────────────
  calibrate: (ppm) => request('POST', `/api/calibrate/pixels_per_mm?pixels_per_mm=${ppm}`),

  // ── Camera ───────────────────────────────────────────────────
  snapshotUrl: () => `${BASE}/api/camera/snapshot?t=${Date.now()}`,
  streamUrl:   () => `${BASE}/stream`,
}
