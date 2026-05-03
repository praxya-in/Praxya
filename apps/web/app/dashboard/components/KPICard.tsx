'use client'

interface KPICardProps {
  label: string
  sublabel: string
  value: number | null
  unit: string
  accent?: 'green' | 'amber'
  isLoading?: boolean
}

export default function KPICard({ label, sublabel, value, unit, accent, isLoading }: KPICardProps) {
  const isGreen = accent === 'green'
  
  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: '12px',
        padding: '24px',
        transition: 'border-color 0.2s, background 0.2s',
        cursor: 'default',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--green-border)'
        e.currentTarget.style.background = 'var(--bg-card-hover)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--border)'
        e.currentTarget.style.background = 'var(--bg-card)'
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginBottom: '16px' }}>
        <div style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          color: 'var(--white-muted)',
          letterSpacing: '2px',
          textTransform: 'uppercase'
        }}>
          {label}
        </div>
        <div style={{
          fontFamily: 'var(--font-sans)',
          fontSize: '11px',
          color: 'var(--white-muted)'
        }}>
          {sublabel}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline' }}>
        {isLoading ? (
          <div style={{
            height: '48px',
            width: '120px',
            background: 'linear-gradient(90deg, #1a2030, #1e2838, #1a2030)',
            backgroundSize: '200%',
            animation: 'shimmer 1.5s infinite',
            borderRadius: '4px'
          }} />
        ) : (
          <>
            <span style={{
              fontFamily: 'var(--font-serif)',
              fontSize: '42px',
              fontWeight: 400,
              color: value === null ? 'var(--white-muted)' : (isGreen ? 'var(--green)' : 'var(--white)'),
              textShadow: isGreen && value !== null ? '0 0 20px rgba(34,197,94,0.3)' : 'none'
            }}>
              {value === null ? '—' : value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
            {value !== null && (
              <span style={{
                fontFamily: 'var(--font-sans)',
                fontSize: '14px',
                color: 'var(--white-dim)',
                marginLeft: '6px'
              }}>
                {unit}
              </span>
            )}
          </>
        )}
      </div>
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}} />
    </div>
  )
}
