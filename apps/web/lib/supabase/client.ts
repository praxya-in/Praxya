'use client'

// apps/web/lib/supabase/client.ts
// ─────────────────────────────────────────────────────────
// Browser-side Supabase client.
// Use this ONLY in 'use client' components that need:
//   - Real-time subscriptions
//   - Client-side auth state
//   - Event handlers that read (not write) data
//
// For data fetching: prefer server components + server.ts.
// ─────────────────────────────────────────────────────────

import { createBrowserClient } from '@supabase/ssr'
import type { Database } from '@/lib/supabase/types'

// Singleton pattern — one client instance per browser session
let client: ReturnType<typeof createBrowserClient<Database>> | undefined

export function createClient() {
  if (client) return client

  client = createBrowserClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )

  return client
}