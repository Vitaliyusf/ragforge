'use client'

import { useCallback, useEffect, useState } from 'react'
import { FileText, Loader2, RefreshCw, Upload } from 'lucide-react'
import fileService from '@/features/files/services/fileService'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import { formatFileSize } from '@/lib/formatting/bytes'
import { getFileStatusTone, normalizeFileStatus } from '@/features/files/fileStatus'
import { useI18n } from '@/i18n'

const POLL_INTERVAL_MS = 5000

// Uploader-facing wording. Deliberately vaguer than the admin labels — a user
// only needs to know whether their document is usable yet, not which pipeline
// stage or guardrail it is sitting in.
const UPLOADER_STATUS_LABEL_KEYS = {
  complete: 'status.ready',
  processing: 'status.processing',
  awaiting_review: 'status.underReview',
  rejected: 'status.notAccepted',
  error: 'status.failed',
}

/**
 * A status the backend sends but this table has no wording for falls back
 * to the raw key with its underscores opened out — untranslated on purpose,
 * because inventing Hebrew for an unknown backend state would be a guess.
 */
function uploaderStatusLabel(status, t) {
  const normalized = normalizeFileStatus(status)
  const key = UPLOADER_STATUS_LABEL_KEYS[normalized]
  return key ? t(key) : normalized.replace(/_/g, ' ')
}

export default function UploadTab() {
  const { t } = useI18n()
  const [file, setFile] = useState(null)
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  const [files, setFiles] = useState([])
  const [filesLoaded, setFilesLoaded] = useState(false)
  const [filesError, setFilesError] = useState(null)

  const loadFiles = useCallback(async () => {
    try {
      const data = await fileService.getMyFiles()
      setFiles(data?.files || [])
      setFilesError(null)
    } catch (error) {
      setFilesError(error?.message || t('upload.loadFailed'))
    } finally {
      setFilesLoaded(true)
    }
  }, [t])

  useEffect(() => {
    let cancelled = false
    const poll = async () => {
      if (cancelled) return
      await loadFiles()
    }
    poll()
    const interval = setInterval(poll, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [loadFiles])

  const submit = async (event) => {
    event.preventDefault()
    if (!file) return
    // Capture the form node now: React nulls event.currentTarget once this
    // handler yields at the await below, so reading it afterward throws.
    const form = event.currentTarget
    setLoading(true)
    setStatus(null)
    try {
      await fileService.uploadFile(file)
      setStatus(t('upload.accepted'))
      setFile(null)
      form.reset()
      await loadFiles()
    } catch (error) {
      setStatus(error?.message || t('knowledge.uploadFailed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-5 overflow-y-auto p-6">
      <form onSubmit={submit} className="w-full space-y-5 rounded-2xl border p-7" style={{ borderColor: 'var(--border)', background: 'var(--surface-elevated)' }}>
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-[var(--fg)]">
            <Upload size={20} /> {t('upload.title')}
          </h1>
          <p className="mt-2 text-[15px] text-[var(--fg-soft)]">{t('upload.privacyNote')}</p>
        </div>
        <label className="block">
          <span className="mb-1 block text-[13px] font-medium text-[var(--fg-muted)]">
            {t('upload.chooseFile')}
          </span>
          {/* No `required` here: the submit button is already disabled until a
              file is picked, and the attribute breaks form submission in jsdom. */}
          <input type="file" onChange={(event) => setFile(event.target.files?.[0] || null)} className="block w-full text-[15px] text-[var(--fg-muted)]" />
        </label>
        <Button type="submit" variant="primary" disabled={!file || loading}>
          {t(loading ? 'upload.uploading' : 'upload.submit')}
        </Button>
        {status && <p className="text-[15px] text-[var(--fg-muted)]">{status}</p>}
      </form>

      <div className="w-full rounded-2xl border p-7" style={{ borderColor: 'var(--border)', background: 'var(--surface-elevated)' }}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold text-[var(--fg)]">
              <FileText size={17} /> {t('upload.yourFiles')}
            </h2>
            <p className="mt-1 text-[15px] text-[var(--fg-soft)]">{t('upload.yourFilesDescription')}</p>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={loadFiles}
            leftIcon={<RefreshCw size={13} />}
          >
            {t('common.refresh')}
          </Button>
        </div>

        {filesError ? (
          <p className="mt-4 text-[15px] text-danger">{filesError}</p>
        ) : null}

        {!filesLoaded ? (
          <p className="mt-4 flex items-center gap-2 text-[15px] text-[var(--fg-muted)]">
            <Loader2 size={14} className="animate-spin" /> {t('upload.loadingFiles')}
          </p>
        ) : null}

        {filesLoaded && !filesError && files.length === 0 ? (
          <p className="mt-4 text-[15px] text-[var(--fg-muted)]">{t('upload.noFiles')}</p>
        ) : null}

        {files.length > 0 ? (
          <ul className="mt-4 space-y-2">
            {files.map((item) => (
              <li
                key={item.file_id}
                className="flex items-center justify-between gap-3 rounded-xl border px-4 py-3"
                style={{ borderColor: 'var(--border)' }}
              >
                <div className="min-w-0">
                  {/* The filename is user data: it keeps its own direction. */}
                  <div dir="auto" className="truncate text-start text-[15px] font-medium text-[var(--fg)]">
                    {item.filename || t('upload.unknownFile')}
                  </div>
                  <div className="mt-0.5 text-[13px] text-[var(--fg-muted)]">{formatFileSize(item.size)}</div>
                </div>
                <Badge variant={getFileStatusTone(item.status)}>{uploaderStatusLabel(item.status, t)}</Badge>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  )
}
