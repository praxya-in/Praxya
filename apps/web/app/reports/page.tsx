'use client'

import { useState, useEffect } from 'react'
import { useSearchParams } from 'next/navigation'
import Sidebar from '../dashboard/components/Sidebar'
import FacilitySelector from '../dashboard/components/FacilitySelector'
import { apiPost } from '@/lib/api'
import { createClient } from '@/lib/supabase/client'

export default function ReportsPage() {
  const searchParams = useSearchParams()
  const urlFacilityId = searchParams.get('facility_id')
  const urlPeriodId = searchParams.get('period_id')

  const [facilityId, setFacilityId] = useState(urlFacilityId || '')
  const [periodId, setPeriodId] = useState(urlPeriodId || '')
  const [facilityName, setFacilityName] = useState('Selected Facility')
  const [fyLabel, setFyLabel] = useState('Selected Period')

  const [isGenerating, setIsGenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [successData, setSuccessData] = useState<{ download_url: string, version: number } | null>(null)

  useEffect(() => {
    if (facilityId) {
      const fetchNames = async () => {
        const supabase = createClient()
        const { data: fData } = await supabase.from('facilities').select('name').eq('id', facilityId).single() as { data: any }
        if (fData) setFacilityName(fData.name)
        
        if (periodId) {
          const { data: pData } = await supabase.from('reporting_periods').select('fy_label').eq('id', periodId).single() as { data: any }
          if (pData) setFyLabel(pData.fy_label)
        }
      }
      fetchNames()
    }
  }, [facilityId, periodId])

  const handleGenerate = async () => {
    setIsGenerating(true)
    setError(null)
    setSuccessData(null)

    try {
      const supabase = createClient()
      const { data: { session } } = await supabase.auth.getSession()

      if (!session) {
        setError('Not authenticated')
        setIsGenerating(false)
        return
      }

      const res = await apiPost<{ download_url: string, version: number }>(
        '/api/reports/generate',
        { facility_id: facilityId, reporting_period_id: periodId },
        session.access_token
      )

      setSuccessData(res)
    } catch (err: any) {
      setError(err.message || 'Generation failed')
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <Sidebar />
      <main style={{ flex: 1, overflowY: 'auto' }}>
        <div style={{
          padding: '28px 32px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start'
        }}>
          <div>
            <div style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              color: 'var(--white-muted)',
              marginBottom: '4px'
            }}>
              Dashboard / Reports
            </div>
            <h1 style={{
              fontFamily: 'var(--font-serif)',
              fontSize: '32px',
              fontWeight: 600,
              color: 'var(--white)',
              margin: 0
            }}>
              BRSR Report
            </h1>
          </div>
          {(!urlFacilityId || !urlPeriodId) && (
            <FacilitySelector onSelect={(fid, pid) => {
              setFacilityId(fid)
              setPeriodId(pid)
            }} />
          )}
        </div>

        <div style={{ padding: '28px 32px' }}>
          <div style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: '12px',
            padding: '32px',
            maxWidth: '600px'
          }}>
            <h2 style={{
              fontFamily: 'var(--font-serif)',
              fontSize: '24px',
              color: 'var(--white)',
              margin: '0 0 8px 0',
              fontWeight: 400
            }}>
              Generate BRSR Section C Report
            </h2>
            <div style={{
              fontFamily: 'var(--font-sans)',
              fontSize: '14px',
              color: 'var(--white-dim)'
            }}>
              KPI 1 (GHG Footprint) + KPI 3 (Energy Footprint)
            </div>

            <div style={{
              borderTop: '1px solid var(--border)',
              margin: '24px 0'
            }} />

            <div style={{
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
              marginBottom: '32px'
            }}>
              <div style={{ display: 'flex' }}>
                <span style={{ width: '80px', color: 'var(--white-muted)' }}>Facility:</span>
                <span style={{ color: 'var(--white)' }}>{facilityId ? facilityName : '—'}</span>
              </div>
              <div style={{ display: 'flex' }}>
                <span style={{ width: '80px', color: 'var(--white-muted)' }}>Period:</span>
                <span style={{ color: 'var(--white)' }}>{periodId ? fyLabel : '—'}</span>
              </div>
              <div style={{ display: 'flex' }}>
                <span style={{ width: '80px', color: 'var(--white-muted)' }}>Format:</span>
                <span style={{ color: 'var(--white)' }}>BRSR Section C — Principle 9</span>
              </div>
              <div style={{ display: 'flex' }}>
                <span style={{ width: '80px', color: 'var(--white-muted)' }}>Output:</span>
                <span style={{ color: 'var(--white)' }}>PDF with data lineage footnotes</span>
              </div>
            </div>

            {!isGenerating && !successData && !error && (
              <button
                onClick={handleGenerate}
                disabled={!facilityId || !periodId}
                style={{
                  width: '100%',
                  height: '48px',
                  background: 'var(--green)',
                  color: '#000',
                  fontFamily: 'var(--font-sans)',
                  fontSize: '16px',
                  fontWeight: 600,
                  letterSpacing: '0.3px',
                  borderRadius: '8px',
                  border: 'none',
                  cursor: (!facilityId || !periodId) ? 'not-allowed' : 'pointer',
                  opacity: (!facilityId || !periodId) ? 0.4 : 1
                }}
              >
                Generate Audit-Ready PDF →
              </button>
            )}

            {isGenerating && (
              <div style={{
                width: '100%',
                height: '48px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
                color: 'var(--green)'
              }}>
                <style dangerouslySetInnerHTML={{__html: `
                  @keyframes pulse-dot {
                    0% { transform: scale(0.8); opacity: 0.5; }
                    50% { transform: scale(1.2); opacity: 1; }
                    100% { transform: scale(0.8); opacity: 0.5; }
                  }
                `}} />
                <div style={{
                  width: '8px',
                  height: '8px',
                  background: 'var(--green)',
                  borderRadius: '50%',
                  animation: 'pulse-dot 1s infinite'
                }} />
                Generating PDF... 10–15 seconds
              </div>
            )}

            {successData && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{
                  fontFamily: 'var(--font-sans)',
                  fontSize: '16px',
                  color: 'var(--green)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}>
                  ✓ Report ready — FY {fyLabel}
                  <span style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: '10px',
                    color: 'var(--amber)',
                    background: 'rgba(245,158,11,0.1)',
                    padding: '2px 6px',
                    borderRadius: '4px'
                  }}>
                    v{successData.version}
                  </span>
                </div>
                <button
                  onClick={() => window.open(successData.download_url, '_blank')}
                  style={{
                    width: '100%',
                    height: '48px',
                    background: 'transparent',
                    color: 'var(--green)',
                    border: '1px solid var(--green)',
                    fontFamily: 'var(--font-sans)',
                    fontSize: '16px',
                    fontWeight: 600,
                    borderRadius: '8px',
                    cursor: 'pointer'
                  }}
                >
                  Download PDF
                </button>
              </div>
            )}

            {error && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ color: 'var(--red)', fontFamily: 'var(--font-sans)', fontSize: '14px' }}>
                  {error}
                </div>
                <button
                  onClick={() => setError(null)}
                  style={{
                    width: '100%',
                    height: '48px',
                    background: 'transparent',
                    color: 'var(--white)',
                    border: '1px solid var(--border)',
                    fontFamily: 'var(--font-sans)',
                    fontSize: '16px',
                    borderRadius: '8px',
                    cursor: 'pointer'
                  }}
                >
                  Retry
                </button>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
