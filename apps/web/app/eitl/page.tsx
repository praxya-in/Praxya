// apps/web/app/eitl/page.tsx
// ─────────────────────────────────────────────────────────
// EITL Review Page — server component wrapper + client component.
// Reads job_id from URL search params.
// Fetches job + extraction data on mount.
// Renders two-panel layout: DocumentViewer (60%) + ExtractionEditor (40%).
//
// NO <form> tags. (Rule 8)
// ─────────────────────────────────────────────────────────

import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import EitlClient from './EitlClient'

export const metadata = {
  title: 'Review Extraction — Praxya',
  description: 'Review and approve AI-extracted data from uploaded documents.',
}

export default async function EitlPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login?redirect=/eitl')
  }

  return <EitlClient />
}
