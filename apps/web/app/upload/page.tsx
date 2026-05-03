// apps/web/app/upload/page.tsx
// ─────────────────────────────────────────────────────────
// Upload Portal — server component wrapper + client component.
// 1. Server component checks auth (middleware already handles redirect).
// 2. Client component renders upload form with:
//    - Facility selector (fetched from Supabase)
//    - Document type selector
//    - Period date range
//    - DropZone for file selection
//    - UploadProgress after upload completes
//
// NO <form> tags. onClick handlers only. (Rule 8)
// ─────────────────────────────────────────────────────────

import { createClient } from '@/lib/supabase/server'
import { redirect } from 'next/navigation'
import UploadClient from './UploadClient'

export const metadata = {
  title: 'Upload Document — Praxya',
  description: 'Upload electricity bills, fuel invoices, or production logs for GHG analysis.',
}

export default async function UploadPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login?redirect=/upload')
  }

  return <UploadClient />
}
