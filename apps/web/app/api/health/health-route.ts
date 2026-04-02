// apps/web/src/app/api/health/route.ts
// ─────────────────────────────────────────────────────────
// GET /api/health
// Returns DB connectivity status and table list.
// Use this to verify Supabase is wired correctly.
// No auth required — excluded from middleware matcher.
// ─────────────────────────────────────────────────────────

import { NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase/server'

export async function GET() {
  try {
    const supabase = createServiceClient()

    // Check we can query each MVP table
    const checks = await Promise.all([
      supabase.from('organisations').select('id').limit(1),
      supabase.from('facilities').select('id').limit(1),
      supabase.from('reporting_periods').select('id').limit(1),
      supabase.from('emission_inputs').select('id').limit(1),
      supabase.from('emission_results').select('id').limit(1),
      supabase.from('emission_factors').select('id').limit(1),
      supabase.from('regulatory_corpus').select('id').limit(1),
    ])

    const tables = [
      'organisations',
      'facilities',
      'reporting_periods',
      'emission_inputs',
      'emission_results',
      'emission_factors',
      'regulatory_corpus',
    ]

    const errors = checks
      .map((r, i) => r.error ? `${tables[i]}: ${r.error.message}` : null)
      .filter(Boolean)

    if (errors.length > 0) {
      return NextResponse.json(
        { status: 'error', db: 'partially_connected', errors },
        { status: 500 }
      )
    }

    // Check emission_factors seed data
    const { data: factors } = await supabase
      .from('emission_factors')
      .select('fuel_or_activity, co2e_per_unit, unit')
      .eq('is_active', true)
      .order('fuel_or_activity')

    return NextResponse.json({
      status: 'ok',
      db: 'connected',
      tables,
      emission_factors_loaded: factors?.length ?? 0,
      factors_preview: factors?.slice(0, 3),
      supabase_url: process.env.NEXT_PUBLIC_SUPABASE_URL,
      timestamp: new Date().toISOString(),
    })
  } catch (err) {
    return NextResponse.json(
      {
        status: 'error',
        db: 'unreachable',
        message: err instanceof Error ? err.message : String(err),
        hint: 'Is `supabase start` running? Check DB_URL and SUPABASE_SERVICE_ROLE_KEY in .env.local',
      },
      { status: 500 }
    )
  }
}