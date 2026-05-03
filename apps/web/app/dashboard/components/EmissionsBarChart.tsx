'use client'

interface ChartData {
  label: string
  value: number
  color?: string
}

export default function EmissionsBarChart({ data }: { data?: ChartData[] }) {
  const defaultData: ChartData[] = [
    { label: 'H₂SO₄', value: 1410 },
    { label: 'Boiler', value: 980 },
    { label: 'DG Set', value: 412 },
    { label: 'Grid', value: 1717 },
    { label: 'Transp.', value: 302 }
  ]

  const chartData = data && data.length > 0 ? data : defaultData
  const maxValue = Math.max(...chartData.map(d => d.value)) || 1

  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: '12px', height: '120px' }}>
      {chartData.map((item, idx) => {
        const heightPct = (item.value / maxValue) * 100
        return (
          <div key={idx} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%' }}>
            <div style={{ flex: 1, display: 'flex', alignItems: 'flex-end', width: '100%', position: 'relative' }} className="bar-container">
              <div 
                className="bar"
                style={{
                  width: '100%',
                  height: `${heightPct}%`,
                  background: item.color || 'var(--green)',
                  opacity: 0.7,
                  borderRadius: '4px 4px 0 0',
                  transition: 'opacity 0.2s, transform 0.2s',
                  transformOrigin: 'bottom'
                }}
              />
              <div className="tooltip">
                {item.value.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
              </div>
            </div>
            <div style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '9px',
              color: 'var(--white-muted)',
              textAlign: 'center',
              marginTop: '6px',
              width: '100%',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis'
            }}>
              {item.label.length > 8 ? item.label.substring(0, 8) + '...' : item.label}
            </div>
          </div>
        )
      })}
      <style dangerouslySetInnerHTML={{__html: `
        .bar-container {
          position: relative;
        }
        .bar-container:hover .bar {
          opacity: 1 !important;
          transform: scaleY(1.02) !important;
        }
        .tooltip {
          position: absolute;
          bottom: 100%;
          left: 50%;
          transform: translateX(-50%);
          margin-bottom: 4px;
          background: var(--bg-secondary);
          border: 1px solid var(--green-border);
          font-family: var(--font-mono);
          font-size: 11px;
          color: var(--green);
          padding: 4px 8px;
          border-radius: 4px;
          opacity: 0;
          pointer-events: none;
          transition: opacity 0.2s;
          white-space: nowrap;
          z-index: 10;
        }
        .bar-container:hover .tooltip {
          opacity: 1;
        }
      `}} />
    </div>
  )
}
