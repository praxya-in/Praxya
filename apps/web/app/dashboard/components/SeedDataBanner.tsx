'use client'

export default function SeedDataBanner({ isVisible }: { isVisible: boolean }) {
  if (!isVisible) return null

  return (
    <div style={{
      width: '100%',
      background: 'rgba(245, 158, 11, 0.08)',
      borderBottom: '1px solid rgba(245,158,11,0.3)',
      padding: '10px 24px',
      fontFamily: 'var(--font-mono)',
      fontSize: '11px',
      color: '#fbbf24',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center'
    }}>
      <span>
        ⚠ DEMO DATA — Fictional companies — Numbers are illustrative. Not for submission to SEBI.
      </span>
    </div>
  )
}
