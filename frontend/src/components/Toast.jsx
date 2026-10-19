const ICONS = { success: '✅', warning: '⚠️', danger: '🚨', info: 'ℹ️' }

export default function Toast({ toasts, onRemove }) {
  return (
    <div id="toast-root">
      {toasts.map(t => (
        <div key={t.id} className={`toast ${t.type}`}>
          <span style={{ fontSize: 16, flexShrink: 0 }}>{ICONS[t.type] || 'ℹ️'}</span>
          <span style={{ flex: 1, color: 'var(--text-primary)' }}>{t.message}</span>
          <button
            onClick={() => onRemove(t.id)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: 12, padding: '0 2px' }}
          >✕</button>
        </div>
      ))}
    </div>
  )
}
