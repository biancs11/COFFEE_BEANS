import { useLocation, useNavigate } from 'react-router-dom'
import clsx from 'clsx'

const NAV = [
  { path: '/overview',    icon: '🏠', label: 'Overview'    },
  { path: '/detection',   icon: '📷', label: 'Detection'   },
  { path: '/assessment',  icon: '🤖', label: 'Assessment'  },
  { path: '/sorting',     icon: '📦', label: 'Sorting'     },
  { path: '/errors',      icon: '🚨', label: 'Alerts'      },
  { path: '/dashboard',   icon: '📊', label: 'Dashboard'   },
]

export default function Sidebar({ alertCount = 0 }) {
  const { pathname } = useLocation()
  const navigate     = useNavigate()

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">☕</div>
      <div className="sidebar-divider" />

      {NAV.map(n => (
        <button
          key={n.path}
          title={n.label}
          onClick={() => navigate(n.path)}
          className={clsx('neu-icon-btn', pathname === n.path && 'active')}
          style={{ position: 'relative', width: 46, height: 46, fontSize: 18 }}
        >
          {n.icon}
          {/* Alert badge on errors nav */}
          {n.path === '/errors' && alertCount > 0 && (
            <span style={{
              position: 'absolute', top: 4, right: 4,
              width: 16, height: 16,
              background: 'var(--danger)',
              borderRadius: '50%',
              fontSize: '0.55rem',
              fontWeight: 700,
              color: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 6px rgba(239,68,68,0.5)',
            }}>
              {alertCount > 9 ? '9+' : alertCount}
            </span>
          )}
        </button>
      ))}

      <div style={{ flex: 1 }} />
      <div className="sidebar-divider" />

      {/* Settings */}
      <button
        title="Settings"
        onClick={() => navigate('/settings')}
        className={clsx('neu-icon-btn', pathname === '/settings' && 'active')}
        style={{ width: 46, height: 46, fontSize: 18 }}
      >
        ⚙️
      </button>
    </aside>
  )
}
