'use client'

import { useRef, useState } from 'react'
import Button from '@/components/ui/Button'
import Input, { Textarea } from '@/components/ui/Input'
import Modal from '@/components/ui/Modal'
import metricsService from '../../services/metricsService'
import GoldenSetValidationResult from './GoldenSetValidationResult'
import { useI18n } from '@/i18n'
import { DEFAULT_LOCALE } from '@/i18n/locale'
import { translate } from '@/i18n/translate'

export const MAX_GOLDEN_SET_BYTES = 5 * 1024 * 1024

function utf8Size(value) {
  return new TextEncoder().encode(value).byteLength
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error(translate(DEFAULT_LOCALE, 'importer.fileUnreadable')))
    reader.readAsText(file, 'UTF-8')
  })
}

export default function GoldenSetImporter({ open, onOpenChange, onSubmit, busy = false, error }) {
  const { t } = useI18n()
  const fileInputRef = useRef(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [format, setFormat] = useState('json')
  const [content, setContent] = useState('')
  const [validation, setValidation] = useState(null)
  const [localError, setLocalError] = useState(null)
  const [validating, setValidating] = useState(false)

  const invalidate = () => {
    setValidation(null)
    setLocalError(null)
  }

  const reset = () => {
    setName('')
    setDescription('')
    setFormat('json')
    setContent('')
    setValidation(null)
    setLocalError(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleOpenChange = (next) => {
    if (!next && !busy && !validating) reset()
    onOpenChange(next)
  }

  const handleFile = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    invalidate()
    if (!/\.(json|jsonl)$/i.test(file.name)) {
      setContent('')
      setLocalError(t('importer.wrongExtension'))
      return
    }
    if (file.size > MAX_GOLDEN_SET_BYTES) {
      setContent('')
      setLocalError(t('importer.fileTooLarge'))
      return
    }
    try {
      const text = await readFile(file)
      setFormat(file.name.toLowerCase().endsWith('.jsonl') ? 'jsonl' : 'json')
      setContent(text)
    } catch (error) {
      setContent('')
      setLocalError(error.message)
    }
  }

  const handleValidate = async () => {
    if (!content.trim()) return
    if (utf8Size(content) > MAX_GOLDEN_SET_BYTES) {
      setValidation(null)
      setLocalError(t('importer.contentTooLarge'))
      return
    }
    setValidating(true)
    setLocalError(null)
    try {
      const response = await metricsService.validateGoldenSet({ content, format })
      setValidation(
        response?.validation
          ? { ...response.validation, preparation: response?.preparation || null }
          : null
      )
    } catch (error) {
      setValidation(null)
      setLocalError(error?.message || t('importer.validateFailed'))
    } finally {
      setValidating(false)
    }
  }

  const handleImport = async () => {
    const imported = await onSubmit({
      name: name.trim(),
      description: description.trim() || null,
      content,
      format,
    })
    if (imported) {
      reset()
      onOpenChange(false)
    }
  }

  return (
    <Modal open={open} onOpenChange={handleOpenChange} title={t('importer.title')} size="lg">
      <div className="flex flex-col gap-3">
        <Input
          label={t('importer.name')}
          aria-label={t('importer.name')}
          // A dataset name is the reader's own; a description likewise.
          dir="auto"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <Input
          label={t('importer.description')}
          aria-label={t('importer.description')}
          dir="auto"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />

        <div className="grid gap-3 sm:grid-cols-[1fr_140px]">
          <div className="flex flex-col gap-1">
            <label htmlFor="golden-set-file" className="text-[13px] font-medium" style={{ color: 'var(--fg-muted)' }}>
              {t('importer.uploadLabel')}
            </label>
            <input
              ref={fileInputRef}
              id="golden-set-file"
              type="file"
              accept=".json,.jsonl,application/json,application/x-ndjson"
              onChange={handleFile}
              disabled={busy || validating}
              aria-describedby="golden-set-size-hint"
              className="text-[13px] file:me-3 file:rounded-lg file:border file:border-[var(--border)] file:bg-[var(--secondary)] file:px-3 file:py-1.5 file:text-[13px] file:text-[var(--fg-muted)]"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label htmlFor="golden-set-format" className="text-[13px] font-medium" style={{ color: 'var(--fg-muted)' }}>
              {t('importer.pastedFormat')}
            </label>
            <select
              id="golden-set-format"
              value={format}
              onChange={(event) => {
                setFormat(event.target.value)
                invalidate()
              }}
              className="h-9 rounded-lg border px-3 text-[15px] outline-hidden focus:ring-2 focus:ring-[var(--ring)]"
              style={{ background: 'var(--surface)', borderColor: 'var(--border)', color: 'var(--fg)' }}
            >
              <option value="json">JSON</option>
              <option value="jsonl">JSONL</option>
            </select>
          </div>
        </div>
        <p id="golden-set-size-hint" className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
          {t('importer.sizeHint')}
        </p>

        <Textarea
          label={t('importer.content')}
          aria-label={t('importer.content')}
          // JSON is a technical artifact: LTR and left-aligned always.
          dir="ltr"
          className="text-left"
          rows={10}
          value={content}
          onChange={(event) => {
            setContent(event.target.value)
            invalidate()
          }}
          disabled={busy || validating}
          placeholder='[{"query":"What is the refund window?","relevant_chunk_ids":["chunk-1"]}]'
        />

        <GoldenSetValidationResult result={validation} error={localError || error} />

        <div className="flex flex-wrap justify-between gap-2">
          <Button variant="ghost" onClick={reset} disabled={busy || validating}>
            {t('common.clear')}
          </Button>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => handleOpenChange(false)} disabled={busy || validating}>
              {t('common.cancel')}
            </Button>
            <Button
              variant="secondary"
              onClick={handleValidate}
              loading={validating}
              disabled={busy || !content.trim()}
            >
              {t('importer.validate')}
            </Button>
            <Button
              onClick={handleImport}
              loading={busy}
              disabled={!validation?.valid || !name.trim() || validating}
            >
              {t('importer.import')}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  )
}
