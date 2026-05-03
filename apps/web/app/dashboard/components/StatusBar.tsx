'use client'

interface StatusBarProps {
  isComplete: boolean
  dataPoints: number
  isXBRLReady: boolean
  isCAPortalActive: boolean
}

export default function StatusBar({ isComplete, dataPoints, isXBRLReady, isCAPortalActive }: StatusBarProps) {
  return (
    <div style={{
      width: '100%',
      height: '40px',
      background: 'rgba(34,197,94,0.06)',
      borderTop: '1px solid var(--green-border)',
      display: 'flex',
      alignItems: 'center',
      gap: '24px',
      padding: '0 24px'
    }}>
      <style dangerouslySetInnerHTML={{__html: `
        @keyframes pulse {
          0% { box-shadow: 0 0 0 0 rgba(34,197,94,0.6); }
          70% { box-shadow: 0 0 0 6px rgba(34,197,94,0); }
          100% { box-shadow: 0 0 0 0 rgba(34,197,94,0); }
        }
      `}} />
      
      {isComplete && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{
            width: '6px',
            height: '6px',
            background: 'var(--green)',
            borderRadius: '50%',
            animation: 'pulse 2s infinite'
          }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--green)' }}>
            ✓ Report complete
          </span>
        </div>
      )}

      {isComplete && <span style={{ color: 'var(--white-muted)', opacity: 0.4 }}>·</span>}

      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--white-muted)' }}>
        {dataPoints} data points
      </span>

      {isXBRLReady && (
        <>
          <span style={{ color: 'var(--white-muted)', opacity: 0.4 }}>·</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--green)' }}>
            XBRL ready
          </span>
        </>
      )}

      {isCAPortalActive && (
        <>
          <span style={{ color: 'var(--white-muted)', opacity: 0.4 }}>·</span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--green)' }}>
            CA portal active
          </span>
        </>
      )}
    </div>
  )
}
