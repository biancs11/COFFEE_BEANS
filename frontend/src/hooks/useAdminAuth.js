/**
 * useAdminAuth — manages admin authentication state.
 *
 * Token is stored in sessionStorage so it:
 *   - Persists across page refreshes within the same tab
 *   - Is automatically cleared when the browser tab is closed
 *   - Is NOT shared between tabs (each tab needs its own login)
 *
 * On mount, verifies the stored token against the backend.
 * If the token is expired or invalid, clears it and shows the login gate.
 */

import { useState, useEffect, useCallback } from 'react'

const BASE = import.meta.env.VITE_API_URL || ''

const STORAGE_TOKEN = 'admin_token'
const STORAGE_USER  = 'admin_username'

export function useAdminAuth() {
  const [token,    setToken]    = useState(() => sessionStorage.getItem(STORAGE_TOKEN) || null)
  const [username, setUsername] = useState(() => sessionStorage.getItem(STORAGE_USER)  || null)
  const [verified, setVerified] = useState(false)   // true once backend confirmed the token
  const [checking, setChecking] = useState(true)    // true while verifying on mount

  // Verify stored token against backend on mount
  useEffect(() => {
    if (!token) {
      setChecking(false)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`${BASE}/api/admin/verify?token=${encodeURIComponent(token)}`)
        if (!cancelled) {
          if (res.ok) {
            setVerified(true)
          } else {
            // Token invalid or expired — clear it
            clearAuth()
          }
        }
      } catch {
        if (!cancelled) clearAuth()
      } finally {
        if (!cancelled) setChecking(false)
      }
    })()
    return () => { cancelled = true }
  }, [])  // run only on mount

  const login = useCallback((newToken, newUsername) => {
    sessionStorage.setItem(STORAGE_TOKEN, newToken)
    sessionStorage.setItem(STORAGE_USER,  newUsername)
    setToken(newToken)
    setUsername(newUsername)
    setVerified(true)
    setChecking(false)
  }, [])

  const logout = useCallback(() => {
    clearAuth()
  }, [])

  function clearAuth() {
    sessionStorage.removeItem(STORAGE_TOKEN)
    sessionStorage.removeItem(STORAGE_USER)
    setToken(null)
    setUsername(null)
    setVerified(false)
  }

  const isAuthenticated = !!token && verified

  return { isAuthenticated, username, checking, login, logout }
}
