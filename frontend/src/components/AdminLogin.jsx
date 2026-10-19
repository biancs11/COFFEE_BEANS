import { useState } from 'react'

const BASE = import.meta.env.VITE_API_URL || ''

export default function AdminLogin({ onSuccess }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error,    setError]    = useState('')
  const [loading,  setLoading]  = useState(false)
  const [showPass, setShowPass] = useState(false)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) {
      setError('Please enter both username and password.')
      return
    }
    setLoading(true)
    setError('')
    try {
      const res = await fetch(`${BASE}/api/admin/login`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ username: username.trim(), password }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.detail || 'Login failed. Please try again.')
        return
      }
      // Store token in sessionStorage — cleared when tab closes
      sessionStorage.setItem('admin_token',    data.token)
      sessionStorage.setItem('admin_username', data.username)
      onSuccess(data.token, data.username)
    } catch (err) {
      setError('Cannot reach server. Ensure the backend is running.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="admin-login-overlay">
      <div className="admin-login-card">

        {/* Header */}
        <div className="admin-login-header">
          <div className="admin-login-icon">🔐</div>
          <h2 className="admin-login-title">Admin Access</h2>
          <p className="admin-login-sub">
            This dashboard is restricted to authorized administrators only.
          </p>
        </div>

        {/* Form */}
        <form className="admin-login-form" onSubmit={handleSubmit} autoComplete="off">

          <div className="admin-login-field">
            <label className="admin-login-label">Username</label>
            <input
              className="neu-input admin-login-input"
              type="text"
              placeholder="Enter admin username"
              value={username}
              onChange={e => { setUsername(e.target.value); setError('') }}
              autoFocus
              autoComplete="username"
            />
          </div>

          <div className="admin-login-field">
            <label className="admin-login-label">Password</label>
            <div style={{ position: 'relative' }}>
              <input
                className="neu-input admin-login-input"
                type={showPass ? 'text' : 'password'}
                placeholder="Enter admin password"
                value={password}
                onChange={e => { setPassword(e.target.value); setError('') }}
                autoComplete="current-password"
                style={{ paddingRight: 40 }}
              />
              <button
                type="button"
                className="admin-login-eye"
                onClick={() => setShowPass(s => !s)}
                tabIndex={-1}
              >
                {showPass ? '🙈' : '👁️'}
              </button>
            </div>
          </div>

          {/* Error message */}
          {error && (
            <div className="admin-login-error">
              <span>⚠️</span> {error}
            </div>
          )}

          <button
            type="submit"
            className="neu-btn neu-btn-primary admin-login-btn"
            disabled={loading}
          >
            {loading ? (
              <>
                <span className="admin-login-spinner" />
                Verifying…
              </>
            ) : (
              <>🔓 Sign In to Admin Dashboard</>
            )}
          </button>
        </form>

        {/* Footer */}
        <div className="admin-login-footer">
          <span>🔒</span>
          <span>Secured · Session expires after 8 hours</span>
        </div>

      </div>
    </div>
  )
}
