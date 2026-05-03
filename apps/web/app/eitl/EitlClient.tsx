'use client'

// apps/web/app/eitl/EitlClient.tsx
// ─────────────────────────────────────────────────────────
// Client component for the EITL review workflow.
// Reads job_id from URL search params.
// Fetches job data + extraction on mount.
// Two-panel layout: DocumentViewer (60%) + ExtractionEditor (40%).
// ─────────────────────────────────────────────────────────

import { useState, useEffect, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { apiGet, ApiError } from '@/lib/api'
import DocumentViewer from './components/DocumentViewer'
import ExtractionEditor from './components/ExtractionEditor'

interface JobData {
  job_id: string
  document_id: string
  status: string
  error_message: string | null
  retry_count: number | null
  created_at: string | null
  updated_at: string | null
  extraction?: {
    id: string
    document_id: string
    structured_data: Record<string, string | number | null>
    field_confidences: Record<string, number>
    overall_confidence: number
    llm_model: string | null
    is_human_reviewed: boolean
    reviewed_by: string | null
    created_at: string
  }
}

interface DocumentData {
  id: string
  storage_path: string
  doc_type: string
  facility_id: string
}

// Status messages for non-reviewable states
const STATUS_MESSAGES: Record<string, { title: string; desc: string; icon: string }> = {
  queued: {
    title: 'Document Queued',
    desc: 'Your document is waiting in the processing queue. Please check back shortly.',
    icon: '⏳',
  },
  ocr_processing: {
    title: 'OCR Processing',
    desc: 'We are currently extracting text from your document using OCR.',
    icon: '🔍',
  },
  llm_extracting: {
    title: 'AI Extraction in Progress',
    desc: 'Our AI is extracting structured data from the document text. This usually takes 30–60 seconds.',
    icon: '🤖',
  },
  approved: {
    title: 'Already Approved',
    desc: 'This extraction has already been reviewed and approved.',
    icon: '✓',
  },
  failed: {
    title: 'Processing Failed',
    desc: 'This document failed during processing. You may re-upload it.',
    icon: '✕',
  },
  permanently_failed: {
    title: 'Permanently Failed',
    desc: 'This document failed after 3 attempts and cannot be retried.',
    icon: '✕',
  },
}

function EitlContent() {
  const searchParams = useSearchParams()
  const jobId = searchParams.get('job_id')

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [jobData, setJobData] = useState<JobData | null>(null)
  const [docData, setDocData] = useState<DocumentData | null>(null)

  useEffect(() => {
    if (!jobId) {
      setLoading(false)
      setError('No job_id provided in the URL.')
      return
    }

    async function fetchData() {
      try {
        const supabase = createClient()
        const {
          data: { session },
        } = await supabase.auth.getSession()

        if (!session) {
          setError('Session expired. Please log in again.')
          setLoading(false)
          return
        }

        // The jobs endpoint uses document_id as the path param.
        // But we only have job_id. We need to first find the document_id.
        // Strategy: query pipeline_jobs from Supabase to get document_id,
        // then call the API.
        const { data: jobRows, error: jobError } = await supabase
          .from('pipeline_jobs')
          .select('id, document_id')
          .eq('id', jobId!)
          .limit(1) as { data: any, error: any }

        if (jobError || !jobRows || jobRows.length === 0) {
          setError('Job not found. Please check the URL and try again.')
          setLoading(false)
          return
        }

        const documentId = jobRows[0].document_id

        // Fetch job status + extraction via API
        const data = await apiGet<JobData>(
          `/api/ingest/jobs/${documentId}`,
          session.access_token
        )
        setJobData(data)

        // Fetch document record to get storage_path
        const { data: docRows, error: docError } = await supabase
          .from('evidence_documents')
          .select('id, storage_path, doc_type, facility_id')
          .eq('id', documentId)
          .limit(1)

        if (!docError && docRows && docRows.length > 0) {
          setDocData(docRows[0] as DocumentData)
        }
      } catch (err) {
        if (err instanceof ApiError) {
          setError(`Failed to load job data (${err.status}): ${err.message}`)
        } else {
          setError('Failed to load job data. Please try again.')
        }
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [jobId])

  // ── Loading state ─────────────────────────────────────────
  if (loading) {
    return (
      <main className="eitl-page">
        <div className="eitl-page__loading">
          <div className="spinner" />
          <p>Loading extraction data…</p>
        </div>
      </main>
    )
  }

  // ── Error state ───────────────────────────────────────────
  if (error) {
    return (
      <main className="eitl-page">
        <div className="eitl-page__error">
          <span className="eitl-page__error-icon">✕</span>
          <p>{error}</p>
          <a href="/upload" className="btn btn--primary">
            ← Back to Upload
          </a>
        </div>
      </main>
    )
  }

  // ── Non-reviewable status ─────────────────────────────────
  if (jobData && jobData.status !== 'awaiting_review') {
    const msg = STATUS_MESSAGES[jobData.status] ?? {
      title: 'Unknown Status',
      desc: `Current status: ${jobData.status}`,
      icon: '❓',
    }
    return (
      <main className="eitl-page">
        <div className="eitl-page__status">
          <span className="eitl-page__status-icon">{msg.icon}</span>
          <h2>{msg.title}</h2>
          <p>{msg.desc}</p>
          {jobData.error_message && (
            <p className="eitl-page__error-msg">{jobData.error_message}</p>
          )}
          <div className="eitl-page__status-actions">
            <a href="/upload" className="btn btn--ghost">
              ← Back to Upload
            </a>
            {jobData.status === 'approved' && (
              <a href="/dashboard" className="btn btn--primary">
                Go to Dashboard →
              </a>
            )}
          </div>
        </div>
      </main>
    )
  }

  // ── Review panel layout ───────────────────────────────────
  if (jobData?.extraction && docData) {
    return (
      <main className="eitl-page">
        <h1 className="eitl-page__title">Review Extraction</h1>
        <p className="eitl-page__subtitle">
          Compare the original document with the AI-extracted data. Edit any fields, then approve or reject.
        </p>
        <div className="eitl-page__panels">
          {/* Left panel: Document viewer (60%) */}
          <div className="eitl-page__panel eitl-page__panel--doc">
            <h2 className="eitl-page__panel-title">Original Document</h2>
            <DocumentViewer storagePath={docData.storage_path} />
          </div>

          {/* Right panel: Extraction editor (40%) */}
          <div className="eitl-page__panel eitl-page__panel--editor">
            <ExtractionEditor
              jobId={jobData.job_id}
              extractionData={{
                structured_data: jobData.extraction.structured_data,
                field_confidences: jobData.extraction.field_confidences,
                overall_confidence: jobData.extraction.overall_confidence,
              }}
            />
          </div>
        </div>
      </main>
    )
  }

  // Fallback: extraction data missing
  return (
    <main className="eitl-page">
      <div className="eitl-page__error">
        <span className="eitl-page__error-icon">⚠</span>
        <p>Extraction data not found for this job.</p>
        <a href="/upload" className="btn btn--primary">
          ← Back to Upload
        </a>
      </div>
    </main>
  )
}

export default function EitlClient() {
  return (
    <Suspense
      fallback={
        <main className="eitl-page">
          <div className="eitl-page__loading">
            <div className="spinner" />
            <p>Loading…</p>
          </div>
        </main>
      }
    >
      <EitlContent />
    </Suspense>
  )
}
