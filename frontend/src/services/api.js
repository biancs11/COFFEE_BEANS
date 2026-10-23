/**
 * API service — REST client for the FastAPI backend.
 * Base URL is empty in production (same origin).
 * In dev, Vite proxy forwards /api → http://localhost:8000.
 */

const BASE = import.meta.env.VITE_API_URL || ''

async function request(method, path, body, timeoutMs) {
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
  }
  // Bound the initial Training screen reads so a stalled backend cannot leave
  // that page in its loading state forever. Other API calls may take longer.
  if (timeoutMs) opts.signal = AbortSignal.timeout(timeoutMs)
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
  getColorCalibration: () => request('GET', '/api/calibration/status'),
  deleteColorCalibration: (grade) => request('DELETE', `/api/calibration/sample/${encodeURIComponent(grade)}`),
  captureColorSample: (grade, x, y) => request('POST', '/api/calibration/sample', { grade, x, y }),
  captureColorHex: (grade, hex) => request('POST', '/api/calibration/sample', { grade, hex }),
  completeColorCalibration: () => request('POST', '/api/calibration/complete'),

  // ── Camera ───────────────────────────────────────────────────
  snapshotUrl: () => `${BASE}/api/camera/snapshot?t=${Date.now()}`,
  getCameraColorBalance: () => request('GET', '/api/camera/color-balance'),
  setCameraColorBalance: (value) => request('POST', '/api/camera/color-balance', { value }),
  streamUrl:   () => `${BASE}/stream`,
  submitBrowserFrame: (blob) => fetch(`${BASE}/api/camera/browser-frame`, {
    method: 'POST',
    headers: { 'Content-Type': 'image/jpeg' },
    body: blob,
  }).then(async res => {
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || `HTTP ${res.status}`)
    return res.json()
  }),

  // ── Training / example images ────────────────────────────────
  getTrainingStatus: () => request('GET', '/api/training/status', undefined, 8000),
  getTrainingImages: () => request('GET', '/api/training/images', undefined, 8000),

  /** Upload one image for the given grade (grade1..grade4).
   *  @param {string} grade  'grade1' | 'grade2' | 'grade3' | 'grade4'
   *  @param {File}   file   Browser File object
   */
  uploadTrainingImage: async (grade, file) => {
    const form = new FormData()
    form.append('grade', grade)
    form.append('file',  file)
    const res = await fetch(`${BASE}/api/training/upload`, { method: 'POST', body: form })
    if (!res.ok) {
      let detail = `HTTP ${res.status}`
      try { detail = (await res.json()).detail || detail } catch (_) {}
      throw new Error(detail)
    }
    return res.json()
  },

  runTraining:   ()                     => request('POST',   '/api/training/train'),
  deleteTrainingImage: (grade, filename) => request('DELETE', `/api/training/images/${encodeURIComponent(grade)}/${encodeURIComponent(filename)}`),
  clearGradeImages:    (grade)           => request('DELETE', `/api/training/images/${encodeURIComponent(grade)}`),
  resetProfiles:       ()                => request('DELETE', '/api/training/profiles'),
}
