import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, useLocation, useNavigate } from 'react-router-dom'
import Navbar         from './components/Navbar'
import Toast          from './components/Toast'
import Landing        from './pages/Landing'
import Dashboard      from './pages/Dashboard'
import AdminDashboard from './pages/AdminDashboard'
import AdminLogin     from './components/AdminLogin'
import Training       from './pages/Training'
import { useWebSocket }  from './hooks/useWebSocket'
import { useToast }      from './hooks/useToast'
import { useAdminAuth }  from './hooks/useAdminAuth'

/* ── Theme helpers ─────────────────────────────────────────── */
function getInitialTheme() {
  try {
    const saved = localStorage.getItem('cbs-theme')
    if (saved === 'dark' || saved === 'light') return saved
  } catch (_) {}
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(theme) {
  if (theme === 'dark') document.documentElement.setAttribute('data-theme', 'dark')
  else                  document.documentElement.removeAttribute('data-theme')
  try { localStorage.setItem('cbs-theme', theme) } catch (_) {}
}

/* ── Main app (navbar + dashboard only) ───────────────────── */
function MainApp({ theme, onToggleTheme }) {
  const { stats, lastBean, frame, alerts, connected } = useWebSocket()
  const { toasts, addToast, removeToast }             = useToast()
  const { isAuthenticated, username, checking, login, logout } = useAdminAuth()
  const location  = useLocation()
  const isAdmin   = location.pathname === '/admin'

  return (
    <div className="app-shell">
      <Navbar
        status={connected ? stats.status : 'stopped'}
        onToast={addToast}
        theme={theme}
        onToggleTheme={onToggleTheme}
        currentPath={location.pathname}
        adminUser={isAuthenticated ? username : null}
        onAdminLogout={logout}
      />

      <div className="main">
        {/* Backend connection banner */}
        {!connected && (
          <div style={{
            background: 'rgba(239,68,68,0.08)',
            borderBottom: '1px solid rgba(239,68,68,0.18)',
            padding: '6px 24px',
            fontSize: '0.72rem',
            color: 'var(--danger)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <div className="status-dot error" />
            Connecting to backend — ensure the FastAPI server is running on port 8000.
          </div>
        )}

        <Routes>
          <Route path="/admin" element={
            /* ── Auth gate ── */
            checking ? (
              /* Verifying stored token... */
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
                <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                  <div className="admin-login-spinner" style={{ margin: '0 auto 12px' }} />
                  Verifying session…
                </div>
              </div>
            ) : isAuthenticated ? (
              <AdminDashboard stats={stats} lastBean={lastBean} username={username} onLogout={logout} />
            ) : (
              <AdminLogin onSuccess={login} />
            )
          } />
          <Route path="/training" element={
            <Training onToast={addToast} />
          } />
          <Route path="/*" element={
            <Dashboard stats={stats} lastBean={lastBean} frame={frame} alerts={alerts} onToast={addToast} />
          } />
        </Routes>
      </div>

      <Toast toasts={toasts} onRemove={removeToast} />
    </div>
  )
}

/* ── Root ──────────────────────────────────────────────────── */
export default function App() {
  const [theme, setTheme] = useState(getInitialTheme)

  useEffect(() => { applyTheme(theme) }, [theme])

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark')

  return (
    <BrowserRouter>
      <Routes>
        {/* Landing splash — no navbar */}
        <Route path="/"        element={<Landing />} />
        <Route path="/landing" element={<Landing />} />
        <Route path="/start"   element={<Landing />} />

        {/* Everything else → dashboard */}
        <Route
          path="/*"
          element={<MainApp theme={theme} onToggleTheme={toggleTheme} />}
        />
      </Routes>
    </BrowserRouter>
  )
}
