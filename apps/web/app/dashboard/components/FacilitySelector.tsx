'use client'

import { useState, useEffect } from 'react'
import { createClient } from '@/lib/supabase/client'

interface Facility {
  id: string
  name: string
}

interface ReportingPeriod {
  id: string
  fy_label: string
}

interface Props {
  onSelect: (facilityId: string, reportingPeriodId: string) => void
}

export default function FacilitySelector({ onSelect }: Props) {
  const [facilities, setFacilities] = useState<Facility[]>([])
  const [periods, setPeriods] = useState<ReportingPeriod[]>([])
  
  const [selectedFacility, setSelectedFacility] = useState('')
  const [selectedPeriod, setSelectedPeriod] = useState('')

  useEffect(() => {
    async function loadFacilities() {
      try {
        const supabase = createClient()
        const { data: { user } } = await supabase.auth.getUser()
        if (!user) return

        const { data: memberships } = await supabase
          .from('org_memberships')
          .select('organisation_id')
          .eq('user_id', user.id)
          .limit(1) as { data: any[] }

        if (!memberships || memberships.length === 0) return

        const orgId = memberships[0].organisation_id

        const { data: facilityRows } = await supabase
          .from('facilities')
          .select('id, name')
          .eq('organisation_id', orgId)
          .order('name') as { data: any[] }

        if (facilityRows) {
          setFacilities(facilityRows)
          if (facilityRows.length > 0) {
            handleFacilityChange(facilityRows[0].id)
          }
        }
      } catch (err) {
        console.error('Failed to load facilities:', err)
      }
    }
    loadFacilities()
  }, [])

  const handleFacilityChange = async (facilityId: string) => {
    setSelectedFacility(facilityId)
    setSelectedPeriod('')
    setPeriods([])
    
    if (!facilityId) return
    
    try {
      const supabase = createClient()
      const { data: periodRows } = await supabase
        .from('reporting_periods')
        .select('id, fy_label')
        .eq('facility_id', facilityId)
        .order('fy_label') as { data: any[] }

      if (periodRows) {
        setPeriods(periodRows)
        if (periodRows.length > 0) {
          setSelectedPeriod(periodRows[0].id)
          onSelect(facilityId, periodRows[0].id)
        }
      }
    } catch (err) {
      console.error('Failed to load reporting periods:', err)
    }
  }

  const handlePeriodChange = (periodId: string) => {
    setSelectedPeriod(periodId)
    if (selectedFacility && periodId) {
      onSelect(selectedFacility, periodId)
    }
  }

  return (
    <div style={{ display: 'flex', gap: '16px' }}>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <label style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          color: 'var(--white-muted)',
          letterSpacing: '1.5px',
          textTransform: 'uppercase',
          marginBottom: '6px'
        }}>
          Facility
        </label>
        <select
          value={selectedFacility}
          onChange={(e) => handleFacilityChange(e.target.value)}
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            color: 'var(--white)',
            fontFamily: 'var(--font-sans)',
            fontSize: '14px',
            padding: '8px 12px',
            borderRadius: '8px',
            outline: 'none'
          }}
          onFocus={(e) => e.target.style.borderColor = 'var(--green)'}
          onBlur={(e) => e.target.style.borderColor = 'var(--border)'}
        >
          <option value="" disabled>Select facility</option>
          {facilities.map(f => (
            <option key={f.id} value={f.id} style={{ background: 'var(--bg-secondary)' }}>
              {f.name}
            </option>
          ))}
        </select>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <label style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          color: 'var(--white-muted)',
          letterSpacing: '1.5px',
          textTransform: 'uppercase',
          marginBottom: '6px'
        }}>
          Reporting Period
        </label>
        <select
          value={selectedPeriod}
          onChange={(e) => handlePeriodChange(e.target.value)}
          disabled={!selectedFacility || periods.length === 0}
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            color: 'var(--white)',
            fontFamily: 'var(--font-sans)',
            fontSize: '14px',
            padding: '8px 12px',
            borderRadius: '8px',
            outline: 'none',
            opacity: (!selectedFacility || periods.length === 0) ? 0.5 : 1
          }}
          onFocus={(e) => e.target.style.borderColor = 'var(--green)'}
          onBlur={(e) => e.target.style.borderColor = 'var(--border)'}
        >
          <option value="" disabled>Select period</option>
          {periods.map(p => (
            <option key={p.id} value={p.id} style={{ background: 'var(--bg-secondary)' }}>
              {p.fy_label}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
