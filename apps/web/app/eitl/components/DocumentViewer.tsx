'use client'

// apps/web/app/eitl/components/DocumentViewer.tsx
// ─────────────────────────────────────────────────────────
// Renders the uploaded document in a browser-native iframe.
// Uses Supabase Storage signed URL (1 hour expiry).
//
// No pdf.js or any PDF library — browser native iframe only.
// Always includes fallback "Open in new tab ↗" link.
// ─────────────────────────────────────────────────────────

import { useState, useEffect } from 'react'
import { createClient } from '@/lib/supabase/client'

interface DocumentViewerProps {
  storagePath: string
}

export default function DocumentViewer({ storagePath }: DocumentViewerProps) {
  const [signedUrl, setSignedUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchSignedUrl() {
      try {
        const supabase = createClient()
        const { data, error: storageError } = await supabase.storage
          .from('documents')
          .createSignedUrl(storagePath, 3600)

        if (storageError) {
          setError(`Failed to load document: ${storageError.message}`)
          return
        }

        if (data?.signedUrl) {
          setSignedUrl(data.signedUrl)
        }
      } catch (err) {
        setError('Failed to load document preview.')
        console.error(err)
      } finally {
        setLoading(false)
      }
    }

    fetchSignedUrl()
  }, [storagePath])

  if (loading) {
    return (
      <div className="doc-viewer doc-viewer--loading">
        <div className="spinner" />
        <p>Loading document preview…</p>
      </div>
    )
  }

  if (error || !signedUrl) {
    return (
      <div className="doc-viewer doc-viewer--error">
        <p>{error ?? 'Could not generate document preview URL.'}</p>
      </div>
    )
  }

  return (
    <div className="doc-viewer">
      <iframe
        src={signedUrl}
        title="Document preview"
        style={{ width: '100%', height: '80vh', border: 'none' }}
      />
      <p className="doc-viewer__fallback">
        PDF not displaying?{' '}
        <a href={signedUrl} target="_blank" rel="noopener noreferrer">
          Open in new tab ↗
        </a>
      </p>
    </div>
  )
}
