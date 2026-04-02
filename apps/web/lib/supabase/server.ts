// apps/web/lib/supabase/server.ts
// ─────────────────────────────────────────────────────────
// Server-side Supabase client.
// Use this in:
//   - Server Components (async components that fetch data)
//   - Route Handlers (app/api/**/route.ts)
//   - Server Actions
//
// NEVER import this in 'use client' components.
// For client components → use client.ts instead.
// ─────────────────────────────────────────────────────────

import { createServerClient } from '@supabase/ssr'
import { createClient as createSupabaseClient } from '@supabase/supabase-js'
import { cookies } from 'next/headers'
import type { Database } from '@/lib/supabase/types'

export async function createClient() {
  const cookieStore = await cookies()

  return createServerClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll()
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) => {
              cookieStore.set(name, value, options)
            })
          } catch {
            // setAll called from Server Component — cookies are read-only.
            // Middleware handles cookie refresh, so this is safe to ignore.
          }
        },
      },
    }
  )
}

// ── Service role client (bypasses RLS) ─────────────────────
// Use ONLY in:
//   - Background workers (ghg_task, ingestion_task)
//   - Admin operations that intentionally bypass RLS
//   - Route handlers that need to write emission_results (system inserts)
//
// NEVER expose to the client or use in server components that handle user data.

export function createServiceClient() {
  return createSupabaseClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,
    {
      auth: {
        autoRefreshToken: false,
        persistSession: false,
      },
    }
  )
}