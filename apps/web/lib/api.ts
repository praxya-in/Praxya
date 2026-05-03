// apps/web/lib/api.ts
// ─────────────────────────────────────────────────────────
// Typed API client for the FastAPI backend.
// BASE_URL comes from NEXT_PUBLIC_API_URL env var.
//
// Auth: passes the user's Supabase JWT as Bearer token.
// The FastAPI backend creates an RLS-scoped Supabase client
// using this token, so all DB queries respect row-level security.
// ─────────────────────────────────────────────────────────

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

// ── ApiError ─────────────────────────────────────────────

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

// ── Internal helpers ─────────────────────────────────────

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let message = `Request failed with status ${res.status}`
    try {
      const body = await res.json()
      if (body.detail) {
        message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      // Response body is not JSON — use default message
    }
    throw new ApiError(message, res.status)
  }
  return res.json() as Promise<T>
}

// ── Public API ───────────────────────────────────────────

/**
 * GET request to the FastAPI backend.
 * @param path  — route path starting with / (e.g. "/api/ingest/jobs/abc")
 * @param token — Supabase access_token (JWT)
 * @param params — optional query string parameters
 */
export async function apiGet<T>(
  path: string,
  token: string,
  params?: Record<string, string>
): Promise<T> {
  const url = new URL(path, BASE_URL)
  if (params) {
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  }

  const res = await fetch(url.toString(), {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  })

  return handleResponse<T>(res)
}

/**
 * POST request with JSON body to the FastAPI backend.
 * @param path  — route path starting with /
 * @param body  — request payload (serialised to JSON)
 * @param token — Supabase access_token (JWT)
 */
export async function apiPost<T>(
  path: string,
  body: unknown,
  token: string
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })

  return handleResponse<T>(res)
}

/**
 * Upload a file via multipart/form-data.
 * DO NOT set Content-Type — the browser sets it automatically
 * with the correct multipart boundary.
 */
export async function apiUploadFile(
  file: File,
  fields: Record<string, string>,
  token: string
): Promise<{ document_id: string; job_id: string; status: string }> {
  const formData = new FormData()
  formData.append('file', file)
  Object.entries(fields).forEach(([k, v]) => formData.append(k, v))

  const res = await fetch(`${BASE_URL}/api/ingest/upload`, {
    method: 'POST',
    headers: {
      // NO Content-Type here — browser sets multipart boundary automatically
      Authorization: `Bearer ${token}`,
    },
    body: formData,
  })

  return handleResponse<{ document_id: string; job_id: string; status: string }>(res)
}
