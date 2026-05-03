'use client'

// apps/web/app/eitl/components/ExtractionEditor.tsx
// ─────────────────────────────────────────────────────────
// Renders extraction data as editable fields with confidence
// color-coding. Handles approve/reject actions.
//
// NO <form> tags. onClick + useState for all interactions. (Rule 8)
// ─────────────────────────────────────────────────────────

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import { apiPost, ApiError } from '@/lib/api'

// ── Field label map ──────────────────────────────────────

const FIELD_LABELS: Record<string, string> = {
  total_units_kwh: 'Electricity consumed (kWh)',
  billing_period_start: 'Bill period start date',
  billing_period_end: 'Bill period end date',
  quantity_litres: 'Fuel quantity (litres)',
  fuel_type: 'Fuel type',
  invoice_date: 'Invoice date',
  quantity_tonnes: 'Production quantity (tonnes)',
  product_name: 'Product name',
  process_id: 'Chemical process',
  period_start: 'Production period start',
  period_end: 'Production period end',
}

function getFieldLabel(key: string): string {
  if (FIELD_LABELS[key]) return FIELD_LABELS[key]
  // Fallback: replace underscores with spaces, capitalize first letter
  return key.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

// ── Confidence helpers ───────────────────────────────────

function getConfidenceClass(confidence: number | undefined): string {
  if (confidence === undefined) return ''
  if (confidence >= 0.85) return 'field--high-confidence'
  if (confidence >= 0.7) return 'field--medium-confidence'
  return 'field--low-confidence'
}

function getConfidenceBorderColor(confidence: number | undefined): string {
  if (confidence === undefined) return 'var(--color-border)'
  if (confidence >= 0.85) return '#22c55e'
  if (confidence >= 0.7) return '#f59e0b'
  return '#ef4444'
}

// ── Props ────────────────────────────────────────────────

interface ExtractionEditorProps {
  jobId: string
  extractionData: {
    structured_data: Record<string, string | number | null>
    field_confidences: Record<string, number>
    overall_confidence: number
  }
}

export default function ExtractionEditor({ jobId, extractionData }: ExtractionEditorProps) {
  const router = useRouter()

  // Editable form values — initialised from structured_data
  const [formValues, setFormValues] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {}
    for (const [key, val] of Object.entries(extractionData.structured_data)) {
      initial[key] = val !== null && val !== undefined ? String(val) : ''
    }
    return initial
  })

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)

  // Rejection UI state
  const [showRejectInput, setShowRejectInput] = useState(false)
  const [rejectionReason, setRejectionReason] = useState('')

  const overallPct = Math.round(extractionData.overall_confidence * 100)
  const fieldKeys = Object.keys(extractionData.structured_data)

  // ── Field change handler ─────────────────────────────────
  const handleFieldChange = (key: string, value: string) => {
    setFormValues((prev) => ({ ...prev, [key]: value }))
  }

  // ── Approve handler ──────────────────────────────────────
  const handleApprove = async () => {
    setSubmitting(true)
    setSubmitError(null)

    try {
      const supabase = createClient()
      const {
        data: { session },
      } = await supabase.auth.getSession()

      if (!session) {
        setSubmitError('Session expired. Please log in again.')
        setSubmitting(false)
        return
      }

      await apiPost(
        `/api/ingest/eitl/${jobId}/approve`,
        { reviewed_data: formValues },
        session.access_token
      )

      router.push('/dashboard')
    } catch (err) {
      if (err instanceof ApiError) {
        setSubmitError(`Approval failed (${err.status}): ${err.message}`)
      } else {
        setSubmitError('Approval failed. Please try again.')
      }
      setSubmitting(false)
    }
  }

  // ── Reject handler ──────────────────────────────────────
  const handleReject = async () => {
    if (!rejectionReason.trim()) {
      setSubmitError('Please provide a reason for rejection.')
      return
    }

    setSubmitting(true)
    setSubmitError(null)

    try {
      const supabase = createClient()
      const {
        data: { session },
      } = await supabase.auth.getSession()

      if (!session) {
        setSubmitError('Session expired. Please log in again.')
        setSubmitting(false)
        return
      }

      await apiPost(
        `/api/ingest/eitl/${jobId}/reject`,
        { reason: rejectionReason },
        session.access_token
      )

      router.push('/upload')
    } catch (err) {
      if (err instanceof ApiError) {
        setSubmitError(`Rejection failed (${err.status}): ${err.message}`)
      } else {
        setSubmitError('Rejection failed. Please try again.')
      }
      setSubmitting(false)
    }
  }

  return (
    <div className="extraction-editor">
      {/* ── Overall confidence ──────────────────── */}
      <div className="extraction-editor__header">
        <h3>Extraction Review</h3>
        <div className="extraction-editor__confidence">
          Overall extraction confidence:{' '}
          <span
            className={`confidence-badge ${
              overallPct >= 85
                ? 'confidence-badge--high'
                : overallPct >= 70
                  ? 'confidence-badge--medium'
                  : 'confidence-badge--low'
            }`}
          >
            {overallPct}%
          </span>
        </div>
      </div>

      {/* ── Editable fields ────────────────────── */}
      <div className="extraction-editor__fields">
        {fieldKeys.map((key) => {
          const confidence = extractionData.field_confidences[key]
          const isLowConfidence = confidence !== undefined && confidence < 0.7

          return (
            <div
              key={key}
              className={`extraction-field ${getConfidenceClass(confidence)}`}
            >
              <label className="extraction-field__label" htmlFor={`field-${key}`}>
                {isLowConfidence && <span className="extraction-field__warning">⚠</span>}
                {getFieldLabel(key)}
                {confidence !== undefined && (
                  <span className="extraction-field__conf-value">
                    ({Math.round(confidence * 100)}%)
                  </span>
                )}
              </label>
              <input
                id={`field-${key}`}
                type="text"
                className="extraction-field__input"
                style={{ borderColor: getConfidenceBorderColor(confidence) }}
                value={formValues[key] ?? ''}
                onChange={(e) => handleFieldChange(key, e.target.value)}
              />
            </div>
          )
        })}
      </div>

      {/* ── Error message ──────────────────────── */}
      {submitError && (
        <div className="extraction-editor__error">
          <span>✕</span> {submitError}
        </div>
      )}

      {/* ── Rejection reason textarea ──────────── */}
      {showRejectInput && (
        <div className="extraction-editor__reject-input">
          <label className="extraction-field__label" htmlFor="reject-reason">
            Reason for rejection
          </label>
          <textarea
            id="reject-reason"
            className="extraction-field__textarea"
            rows={3}
            placeholder="Explain why this extraction is incorrect…"
            value={rejectionReason}
            onChange={(e) => setRejectionReason(e.target.value)}
          />
        </div>
      )}

      {/* ── Action buttons ─────────────────────── */}
      <div className="extraction-editor__actions">
        <button
          className="btn btn--primary btn--lg"
          onClick={handleApprove}
          disabled={submitting}
        >
          {submitting ? 'Submitting…' : '✓ Approve Extraction'}
        </button>

        {!showRejectInput ? (
          <button
            className="btn btn--danger btn--lg"
            onClick={() => setShowRejectInput(true)}
            disabled={submitting}
          >
            ✕ Reject
          </button>
        ) : (
          <button
            className="btn btn--danger btn--lg"
            onClick={handleReject}
            disabled={submitting || !rejectionReason.trim()}
          >
            {submitting ? 'Submitting…' : 'Confirm Rejection'}
          </button>
        )}
      </div>
    </div>
  )
}
