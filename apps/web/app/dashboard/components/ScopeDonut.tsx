'use client'

export default function ScopeDonut({ scope1, scope2 }: { scope1: number, scope2: number }) {
  const total = scope1 + scope2 || 1 // prevent divide by zero
  const scope1Pct = (scope1 / total) * 100

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '16px' }}>
      <div style={{
        width: '100px',
        height: '100px',
        borderRadius: '50%',
        background: `conic-gradient(var(--green) 0% ${scope1Pct}%, rgba(34,197,94,0.25) ${scope1Pct}% 100%)`,
        position: 'relative'
      }}>
        <div style={{
          position: 'absolute',
          inset: '22px',
          background: 'var(--bg-card)',
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '14px',
            color: 'var(--green)'
          }}>
            {Math.round(scope1Pct)}%
          </span>
        </div>
      </div>
      
      <div style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '4px',
        fontFamily: 'var(--font-mono)',
        fontSize: '11px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--green)' }} />
          <span style={{ color: 'var(--white)' }}>Scope 1 · {scope1.toFixed(0)}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'rgba(34,197,94,0.4)' }} />
          <span style={{ color: 'var(--white)' }}>Scope 2 · {scope2.toFixed(0)}</span>
        </div>
      </div>
    </div>
  )
}
