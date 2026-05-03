'use client'

// apps/web/app/upload/components/UploadProgress.tsx
// ─────────────────────────────────────────────────────────
// Polls GET /api/ingest/jobs/{documentId} every 3 seconds.
// Shows a visual pipeline progress bar with stage labels.
// Stops polling when status is 'approved' or 'permanently_failed'.
// ─────────────────────────────────────────────────────────

import { useState, useEffect, useRef } from 'react'
import { createClient } from '@/lib/supabase/client'
import { apiGet } from '@/lib/api'

interface UploadProgressProps {
  documentId: string
  jobId: string
}

interface JobStatus {
  job_id: string
  document_id: string
  status: string
  error_message: string | null
  retry_count: number | null
  created_at: string | null
  updated_at: string | null
  extraction?: Record<string, unknown>
}

const PIPELINE_STAGES = [
  { key: 'queued', label: 'Queued' },
  { key: 'ocr_processing', label: 'OCR Processing' },
  { key: 'llm_extracting', label: 'LLM Extracting' },
  { key: 'awaiting_review', label: 'Awaiting Review' },
  { key: 'approved', label: 'Approved' },
] as const

const TERMINAL_STATUSES = ['approved', 'permanently_failed']
const POLL_INTERVAL_MS = 3000

function getStageIndex(status: string): number {
  const idx = PIPELINE_STAGES.findIndex((s) => s.key === status)
  return idx >= 0 ? idx : -1
}

export default function UploadProgress({ documentId, jobId }: UploadProgressProps) {
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const supabase = createClient()
        const { data: { session } } = await supabase.auth.getSession()
        if (!session) {
          setError('Session expired. Please log in again.')
          return
        }

        const data = await apiGet<JobStatus>(
          `/api/ingest/jobs/${documentId}`,
          session.access_token
        )

        if (!cancelled) {
          setJobStatus(data)
          setError(null)

          // Stop polling on terminal statuses
          if (TERMINAL_STATUSES.includes(data.status)) {
            if (intervalRef.current) {
              clearInterval(intervalRef.current)
              intervalRef.current = null
            }
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to fetch job status')
        }
      }
    }

    // Initial poll immediately
    poll()

    // Set up interval polling at exactly 3 seconds
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS)

    return () => {
      cancelled = true
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [documentId])

  const currentStatus = jobStatus?.status ?? 'queued'
  const currentIndex = getStageIndex(currentStatus)
  const isFailed = currentStatus === 'failed'
  const isPermanentlyFailed = currentStatus === 'permanently_failed'

  return (
    <div className="upload-progress">
      <h3 className="upload-progress__title">Pipeline Progress</h3>

      {/* ── Progress bar ──────────────────────────── */}
      <div className="pipeline-stages">
        {PIPELINE_STAGES.map((stage, idx) => {
          let stageClass = 'pipeline-stage'
          if (idx < currentIndex) stageClass += ' pipeline-stage--done'
          else if (idx === currentIndex && !isFailed && !isPermanentlyFailed)
            stageClass += ' pipeline-stage--active'
          return (
            <div key={stage.key} className={stageClass}>
              <div className="pipeline-stage__dot">
                {idx < currentIndex ? '✓' : idx === currentIndex && !isFailed ? '●' : '○'}
              </div>
              <span className="pipeline-stage__label">{stage.label}</span>
            </div>
          )
        })}
        <div className="pipeline-stages__track">
          <div
            className="pipeline-stages__fill"
            style={{
              width: `${Math.max(0, (currentIndex / (PIPELINE_STAGES.length - 1)) * 100)}%`,
            }}
          />
        </div>
      </div>

      {/* ── awaiting_review state ─────────────────── */}
      {currentStatus === 'awaiting_review' && (
        <div className="upload-progress__ready">
          <span className="upload-progress__checkmark">✓</span>
          <span>Extraction ready for review</span>
          <a
            href={`/eitl?job_id=${jobId}`}
            className="btn btn--primary upload-progress__review-link"
          >
            Review Extraction →
          </a>
        </div>
      )}

      {/* ── approved state ────────────────────────── */}
      {currentStatus === 'approved' && (
        <div className="upload-progress__success">
          <span className="upload-progress__checkmark">✓</span>
          <span>Document approved and processed successfully.</span>
          <a href="/dashboard" className="btn btn--primary">
            Go to Dashboard
          </a>
        </div>
      )}

      {/* ── failed (retryable) state ──────────────── */}
      {isFailed && (
        <div className="upload-progress__error">
          <span className="upload-progress__error-icon">✕</span>
          <p className="upload-progress__error-msg">
            {jobStatus?.error_message ?? 'Processing failed.'}
          </p>
          <p className="upload-progress__support">
            Please contact support or re-upload the document.
          </p>
        </div>
      )}

      {/* ── permanently_failed state ──────────────── */}
      {isPermanentlyFailed && (
        <div className="upload-progress__error upload-progress__error--permanent">
          <span className="upload-progress__error-icon">✕</span>
          <p className="upload-progress__error-msg">
            Processing failed after 3 attempts.
          </p>
          {jobStatus?.error_message && (
            <p className="upload-progress__error-detail">{jobStatus.error_message}</p>
          )}
          <p className="upload-progress__support">
            No retry available. Please contact support with document ID for assistance.
          </p>
        </div>
      )}

      {/* ── Network/session error ─────────────────── */}
      {error && !isFailed && !isPermanentlyFailed && (
        <div className="upload-progress__error">
          <p>{error}</p>
        </div>
      )}
    </div>
  )
}
