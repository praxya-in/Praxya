'use client'

// apps/web/app/upload/UploadClient.tsx
// ─────────────────────────────────────────────────────────
// Client component handling all upload interactions.
//
// On mount: fetches user's organisation facilities from Supabase.
// After upload: shows UploadProgress component.
// NO <form> tags anywhere. onClick handlers only. (Rule 8)
// ─────────────────────────────────────────────────────────

import { useState, useEffect } from 'react'
import { createClient } from '@/lib/supabase/client'
import { apiUploadFile, ApiError } from '@/lib/api'
import DropZone from './components/DropZone'
import UploadProgress from './components/UploadProgress'

interface Facility {
  id: string
  name: string
}

type DocType = 'electricity_bill' | 'fuel_invoice' | 'production_log'

const DOC_TYPE_OPTIONS: { value: DocType; label: string }[] = [
  { value: 'electricity_bill', label: 'Electricity Bill' },
  { value: 'fuel_invoice', label: 'Fuel Invoice' },
  { value: 'production_log', label: 'Production Log' },
]

export default function UploadClient() {
  // ── State ────────────────────────────────────────────────
  const [facilities, setFacilities] = useState<Facility[]>([])
  const [loading, setLoading] = useState(true)
  const [organisationId, setOrganisationId] = useState<string | null>(null)

  const [selectedFacility, setSelectedFacility] = useState('')
  const [docType, setDocType] = useState<DocType>('electricity_bill')
  const [periodFrom, setPeriodFrom] = useState('')
  const [periodTo, setPeriodTo] = useState('')
  const [file, setFile] = useState<File | null>(null)

  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadResult, setUploadResult] = useState<{
    document_id: string
    job_id: string
  } | null>(null)

  // ── Fetch facilities on mount ────────────────────────────
  useEffect(() => {
    async function loadFacilities() {
      try {
        const supabase = createClient()
        const {
          data: { user },
        } = await supabase.auth.getUser()
        if (!user) return

        // Get the user's organisation via org_memberships
        const { data: memberships } = await supabase
          .from('org_memberships')
          .select('organisation_id')
          .eq('user_id', user.id)
          .limit(1) as { data: any }

        if (!memberships || memberships.length === 0) {
          setLoading(false)
          return
        }

        const orgId = memberships[0].organisation_id
        setOrganisationId(orgId)

        // Fetch facilities for this organisation
        const { data: facilityRows } = await supabase
          .from('facilities')
          .select('id, name')
          .eq('organisation_id', orgId)
          .order('name') as { data: any }

        if (facilityRows) {
          setFacilities(facilityRows)
          if (facilityRows.length > 0) {
            setSelectedFacility(facilityRows[0].id)
          }
        }
      } catch (err) {
        console.error('Failed to load facilities:', err)
      } finally {
        setLoading(false)
      }
    }

    loadFacilities()
  }, [])

  // ── Upload handler ───────────────────────────────────────
  const handleUpload = async () => {
    if (!file) return
    if (!selectedFacility) {
      setUploadError('Please select a facility.')
      return
    }
    if (!periodFrom || !periodTo) {
      setUploadError('Please select the billing period dates.')
      return
    }
    if (!organisationId) {
      setUploadError('No organisation found for your account.')
      return
    }

    setUploading(true)
    setUploadError(null)

    try {
      const supabase = createClient()
      const {
        data: { session },
      } = await supabase.auth.getSession()

      if (!session) {
        setUploadError('Session expired. Please log in again.')
        setUploading(false)
        return
      }

      const result = await apiUploadFile(
        file,
        {
          organisation_id: organisationId,
          facility_id: selectedFacility,
          doc_type: docType,
          period_from: periodFrom,
          period_to: periodTo,
        },
        session.access_token
      )

      setUploadResult({
        document_id: result.document_id,
        job_id: result.job_id,
      })
    } catch (err) {
      if (err instanceof ApiError) {
        setUploadError(`Upload failed (${err.status}): ${err.message}`)
      } else {
        setUploadError('Upload failed. Please try again.')
      }
    } finally {
      setUploading(false)
    }
  }

  // ── Render: post-upload progress view ────────────────────
  if (uploadResult) {
    return (
      <main className="upload-page">
        <div className="upload-page__container">
          <h1 className="upload-page__title">Document Uploaded</h1>
          <p className="upload-page__subtitle">
            Your document is being processed through our AI pipeline.
          </p>
          <UploadProgress
            documentId={uploadResult.document_id}
            jobId={uploadResult.job_id}
          />
          <button
            className="btn btn--ghost upload-page__new-upload"
            onClick={() => {
              setUploadResult(null)
              setFile(null)
              setUploadError(null)
            }}
          >
            ← Upload another document
          </button>
        </div>
      </main>
    )
  }

  // ── Render: upload form ──────────────────────────────────
  return (
    <main className="upload-page">
      <div className="upload-page__container">
        <h1 className="upload-page__title">Upload Document</h1>
        <p className="upload-page__subtitle">
          Upload electricity bills, fuel invoices, or production logs for automated
          GHG extraction.
        </p>

        {loading ? (
          <div className="upload-page__loading">
            <div className="spinner" />
            <p>Loading your facilities…</p>
          </div>
        ) : facilities.length === 0 ? (
          <div className="upload-page__empty">
            <p>
              No facilities found for your organisation. Please contact your
              administrator.
            </p>
          </div>
        ) : (
          <div className="upload-form">
            {/* ── Facility selector ──────────────── */}
            <div className="upload-form__field">
              <label className="upload-form__label" htmlFor="facility-select">
                Facility
              </label>
              <select
                id="facility-select"
                className="upload-form__select"
                value={selectedFacility}
                onChange={(e) => setSelectedFacility(e.target.value)}
              >
                {facilities.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </div>

            {/* ── Document type selector ─────────── */}
            <div className="upload-form__field">
              <label className="upload-form__label" htmlFor="doc-type-select">
                Document Type
              </label>
              <select
                id="doc-type-select"
                className="upload-form__select"
                value={docType}
                onChange={(e) => setDocType(e.target.value as DocType)}
              >
                {DOC_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* ── Period date range ──────────────── */}
            <div className="upload-form__row">
              <div className="upload-form__field">
                <label className="upload-form__label" htmlFor="period-from">
                  Period from
                </label>
                <input
                  id="period-from"
                  type="date"
                  className="upload-form__input"
                  value={periodFrom}
                  onChange={(e) => setPeriodFrom(e.target.value)}
                />
              </div>
              <div className="upload-form__field">
                <label className="upload-form__label" htmlFor="period-to">
                  Period to
                </label>
                <input
                  id="period-to"
                  type="date"
                  className="upload-form__input"
                  value={periodTo}
                  onChange={(e) => setPeriodTo(e.target.value)}
                />
              </div>
            </div>

            {/* ── DropZone ──────────────────────── */}
            <DropZone onFileSelected={setFile} selectedFile={file} />

            {/* ── Error message ─────────────────── */}
            {uploadError && (
              <div className="upload-form__error">
                <span>✕</span> {uploadError}
              </div>
            )}

            {/* ── Upload button ─────────────────── */}
            <button
              className="btn btn--primary btn--lg upload-form__submit"
              onClick={handleUpload}
              disabled={uploading || !file}
            >
              {uploading ? (
                <>
                  <span className="spinner spinner--sm" /> Uploading…
                </>
              ) : (
                'Upload & Start Processing'
              )}
            </button>
          </div>
        )}
      </div>
    </main>
  )
}
