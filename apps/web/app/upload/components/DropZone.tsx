'use client'

// apps/web/app/upload/components/DropZone.tsx
// ─────────────────────────────────────────────────────────
// Drag-and-drop + click-to-select file input.
// Accepts: application/pdf, text/csv only.
// Rejects files > 20 MB client-side before hitting the API.
// No <form> tags — onClick handlers only.
// ─────────────────────────────────────────────────────────

import { useState, useRef, useCallback } from 'react'

interface DropZoneProps {
  onFileSelected: (file: File) => void
  selectedFile: File | null
}

const ACCEPTED_TYPES = ['application/pdf', 'text/csv']
const MAX_SIZE_BYTES = 20 * 1024 * 1024 // 20 MB

type DropState = 'idle' | 'drag-over' | 'file-selected' | 'error'

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function DropZone({ onFileSelected, selectedFile }: DropZoneProps) {
  const [state, setState] = useState<DropState>(selectedFile ? 'file-selected' : 'idle')
  const [errorMessage, setErrorMessage] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const validateAndAccept = useCallback(
    (file: File) => {
      // Check MIME type
      if (!ACCEPTED_TYPES.includes(file.type)) {
        setState('error')
        setErrorMessage(
          `"${file.name}" is not a supported file type. Please upload a PDF or CSV file.`
        )
        return
      }

      // Check file size
      if (file.size > MAX_SIZE_BYTES) {
        setState('error')
        setErrorMessage(
          `"${file.name}" is ${formatFileSize(file.size)}. Maximum file size is 20 MB.`
        )
        return
      }

      // Valid file
      setState('file-selected')
      setErrorMessage('')
      onFileSelected(file)
    },
    [onFileSelected]
  )

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setState('drag-over')
  }, [])

  const handleDragLeave = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setState(selectedFile ? 'file-selected' : 'idle')
    },
    [selectedFile]
  )

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      e.stopPropagation()
      const file = e.dataTransfer.files[0]
      if (file) validateAndAccept(file)
    },
    [validateAndAccept]
  )

  const handleClick = () => {
    inputRef.current?.click()
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) validateAndAccept(file)
    // Reset input so the same file can be re-selected
    e.target.value = ''
  }

  const stateClass =
    state === 'drag-over'
      ? 'dropzone dropzone--drag-over'
      : state === 'file-selected'
        ? 'dropzone dropzone--selected'
        : state === 'error'
          ? 'dropzone dropzone--error'
          : 'dropzone'

  return (
    <div
      className={stateClass}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={handleClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') handleClick()
      }}
    >
      {/* Hidden native file input */}
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.csv,application/pdf,text/csv"
        onChange={handleFileChange}
        style={{ display: 'none' }}
        aria-label="Select file to upload"
      />

      {state === 'error' && (
        <div className="dropzone__error">
          <span className="dropzone__error-icon">✕</span>
          <p>{errorMessage}</p>
          <span className="dropzone__retry">Click or drop another file to try again</span>
        </div>
      )}

      {state === 'file-selected' && selectedFile && (
        <div className="dropzone__file-info">
          <span className="dropzone__file-icon">
            {selectedFile.type === 'application/pdf' ? '📄' : '📊'}
          </span>
          <p className="dropzone__filename">{selectedFile.name}</p>
          <p className="dropzone__filesize">{formatFileSize(selectedFile.size)}</p>
          <span className="dropzone__change">Click or drop to change file</span>
        </div>
      )}

      {state === 'drag-over' && (
        <div className="dropzone__prompt">
          <span className="dropzone__drop-icon">⬇</span>
          <p>Drop your file here</p>
        </div>
      )}

      {state === 'idle' && (
        <div className="dropzone__prompt">
          <span className="dropzone__upload-icon">⬆</span>
          <p>
            <strong>Click to select</strong> or drag &amp; drop your file
          </p>
          <span className="dropzone__hint">PDF or CSV — max 20 MB</span>
        </div>
      )}
    </div>
  )
}
