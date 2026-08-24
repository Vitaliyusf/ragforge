'use client'

import { useCallback, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ChevronDown,
  File,
  FolderOpen,
  FileText,
  Image,
  Loader2,
  RefreshCw,
  Search,
  ShieldAlert,
  Trash2,
  Upload,
  History,
} from 'lucide-react'
import { toast } from 'sonner'
import { useFiles } from '@/features/files'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import Badge from '@/components/ui/Badge'
import Input from '@/components/ui/Input'
import PageHeader from '@/components/ui/PageHeader'
import Modal, { ConfirmModal } from '@/components/ui/Modal'
import FileReviewDrawer from './FileReviewDrawer'
import AuditTrailPanel from './AuditTrailPanel'
import fileService from '@/features/files/services/fileService'
import {
  computeEffectiveStatus,
  formatFileSize,
  getEffectiveStatusBadgeVariant,
  getEffectiveStatusLabel,
  getFileStatusBadgeVariant,
  getFileStatusLabel,
  hasReviewPending,
} from '@/utils/common'

// Pipeline stage config — ordered as they execute
const PIPELINE_STAGES = [
  { key: 'extraction', label: 'Extract' },
  { key: 'review', label: 'Review' },
  { key: 'chunking', label: 'Chunk' },
  { key: 'summary', label: 'Summary' },
  { key: 'embedding', label: 'Embed' },
  { key: 'semantic', label: 'Semantic' },
  { key: 'vector', label: 'Vector' },
  { key: 'metadata', label: 'Metadata' },
]

const FILE_FILTERS = [
  { id: 'all', label: 'All files', countKey: 'totalFiles' },
  { id: 'processing', label: 'Processing', countKey: 'processingCount' },
  { id: 'awaiting_review', label: 'Needs review', countKey: 'awaitingReviewCount' },
  { id: 'complete', label: 'Ready', countKey: 'completedCount' },
  { id: 'error', label: 'Errors', countKey: 'errorCount' },
]

const STAGE_DONE_VALUES = new Set(['done', 'complete', 'completed', 'ready', 'skipped', 'not_required'])
const STAGE_RUNNING_VALUES = new Set(['running', 'processing'])

function normalizeStageValue(value) {
  const normalized = String(value ?? 'waiting').toLowerCase()
  if (STAGE_DONE_VALUES.has(normalized)) return 'done'
  if (STAGE_RUNNING_VALUES.has(normalized)) return 'running'
  if (normalized === 'error') return 'error'
  return 'waiting'
}

// Each state carries a texture as well as a colour — solid, pulsing, striped,
// or hollow — so the pipeline stays readable without colour perception.
const STAGE_SEGMENT_STYLES = {
  done: { className: 'bg-success' },
  running: { className: 'bg-warning animate-pulse' },
  error: {
    className: 'bg-danger',
    style: {
      backgroundImage:
        'repeating-linear-gradient(45deg, transparent 0 2px, rgba(255,255,255,0.55) 2px 4px)',
    },
  },
  waiting: { className: 'bg-bg-tertiary border border-border' },
}

function PipelineBar({ stage }) {
  if (!stage || typeof stage !== 'object') return null

  const stages = PIPELINE_STAGES.map(({ key, label }) => ({
    key,
    label,
    value: stage[key] ?? 'waiting',
    state: normalizeStageValue(stage[key]),
  }))

  const doneCount = stages.filter((entry) => entry.state === 'done').length
  const running = stages.find((entry) => entry.state === 'running')
  const failed = stages.filter((entry) => entry.state === 'error')

  // Read out in place of the eight individual segments, which carry no text.
  const summary = [
    `Pipeline: ${doneCount} of ${stages.length} stages complete`,
    running ? `${running.label.toLowerCase()} running` : null,
    failed.length ? `${failed.map((entry) => entry.label.toLowerCase()).join(', ')} failed` : null,
  ]
    .filter(Boolean)
    .join(', ')

  return (
    <div className="mt-3">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-[11px] font-medium text-text-secondary">Pipeline</span>
        <span className="text-[11px] tabular-nums text-text-secondary">
          {doneCount}/{stages.length}
        </span>
      </div>
      <div className="flex gap-1" role="img" aria-label={summary}>
        {stages.map(({ key, label, value, state }) => {
          const segment = STAGE_SEGMENT_STYLES[state]
          return (
            <div key={key} className="group relative flex-1">
              <div className={`h-2 rounded-full ${segment.className}`} style={segment.style} />
              <div className="pointer-events-none absolute bottom-3.5 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-lg border border-border bg-bg-elevated px-2 py-1 text-[11px] font-medium text-text-secondary opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
                {label}: <span className="capitalize text-text-primary">{value}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function getFileTypeIcon(contentType, filename) {
  const type = (contentType || '').toLowerCase()
  const ext = (filename || '').split('.').pop()?.toLowerCase()
  if (type.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)) return Image
  if (type.includes('pdf') || type.startsWith('text/') || ['pdf', 'txt', 'md', 'doc', 'docx'].includes(ext))
    return FileText
  return File
}

// Status is signalled exactly twice per card: this icon chip, and the badge
// beneath it. Anything more turns a single fact into visual noise.
const STATUS_CHIP_STYLES = {
  complete: 'bg-success-soft text-success',
  error: 'bg-danger-soft text-danger',
  awaiting_review: 'bg-warning-soft text-warning',
}

function FileCard({
  file,
  reviewState,
  isDeleting,
  isReingesting,
  isSummaryLoading,
  requiresReview,
  onDeleteClick,
  onOpenReview,
  onOpenSummary,
  onRerunIngestion,
  onOpenAudit,
}) {
  const [expanded, setExpanded] = useState(false)
  const FileIcon = getFileTypeIcon(file.content_type, file.filename)
  const effectiveStatus = computeEffectiveStatus(file)
  const statusLabel = getEffectiveStatusLabel(file)
  const statusVariant = getEffectiveStatusBadgeVariant(file)
  const statusChipClass = STATUS_CHIP_STYLES[effectiveStatus] || 'bg-bg-tertiary text-accent'

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.96 }}
      className={`relative overflow-hidden rounded-2xl border border-border bg-bg-elevated transition-all duration-200 ${
        isDeleting ? 'opacity-50' : 'hover:border-border-hover hover:shadow-lg'
      }`}
    >
      {/* Card header */}
      <div className="flex items-start gap-3 p-4">
        <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${statusChipClass}`}>
          <FileIcon size={18} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-text-primary">{file.filename || 'Unknown'}</div>
              <div className="mt-0.5 flex items-center gap-2">
                <span className="text-xs text-text-secondary">{formatFileSize(file.size)}</span>
                {file.content_type ? (
                  <>
                    <span className="text-text-muted">·</span>
                    <span className="truncate text-xs text-text-secondary">{file.content_type}</span>
                  </>
                ) : null}
              </div>
            </div>
            <button
              onClick={() => onDeleteClick(file)}
              disabled={isDeleting}
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-text-secondary transition hover:bg-danger-soft hover:text-danger disabled:opacity-40"
              aria-label="Delete file"
            >
              {isDeleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
            </button>
          </div>
        </div>
      </div>

      {/* Status badges */}
      <div className="flex flex-wrap items-center gap-1.5 px-4 pb-3">
        <Badge variant={statusVariant}>{statusLabel}</Badge>
        {file.review_status && file.review_status !== 'not_required' ? (
          <Badge variant="default">{String(file.review_status).replace(/_/g, ' ')}</Badge>
        ) : null}
        {reviewState && reviewState !== 'no review' ? (
          <Badge variant="accent">{reviewState}</Badge>
        ) : null}
      </div>

      {/* Pipeline bar */}
      {file.stage ? (
        <div className="px-4 pb-3">
          <PipelineBar stage={file.stage} />
        </div>
      ) : null}

      {/* Action row */}
      <div className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-3">
        {requiresReview ? (
          <button
            onClick={() => onOpenReview(file.file_id)}
            aria-label="Review file"
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-warning transition hover:bg-warning-soft"
          >
            <ShieldAlert size={13} />
            Review
          </button>
        ) : null}
        <button
          onClick={() => onOpenAudit(file.file_id)}
          aria-label="View Audit Trail"
          className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-text-secondary transition hover:bg-bg-tertiary hover:text-text-primary"
        >
          <History size={13} /> Audit
        </button>
        <button
          onClick={() => onOpenSummary(file.file_id)}
          disabled={isSummaryLoading}
          className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-text-secondary transition hover:bg-bg-tertiary hover:text-text-primary disabled:opacity-50"
        >
          {isSummaryLoading ? <Loader2 size={13} className="animate-spin" /> : <FileText size={13} />}
          Summary
        </button>
        <button
          onClick={() => onRerunIngestion(file.file_id)}
          disabled={isReingesting}
          className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-text-secondary transition hover:bg-bg-tertiary hover:text-text-primary disabled:opacity-50"
        >
          {isReingesting ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          Re-ingest
        </button>
        <button
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="ml-auto flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-text-secondary transition hover:bg-bg-tertiary hover:text-text-primary"
        >
          <ChevronDown size={13} className={`transition-transform ${expanded ? 'rotate-180' : ''}`} />
          Details
        </button>
      </div>

      {/* Expandable details */}
      <AnimatePresence>
        {expanded ? (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="space-y-1.5 px-4 pb-4 pt-1">
              {file.owner_display_name || file.owner_email ? (
                <DetailRow label="Owner" value={file.owner_display_name || file.owner_email} />
              ) : null}
              <DetailRow label="File ID" value={file.file_id} mono />
              {file.current_task_id ? (
                <DetailRow label="Task ID" value={file.current_task_id} mono />
              ) : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.div>
  )
}

function DetailRow({ label, value, mono }) {
  return (
    <div className="flex items-start gap-2 rounded-xl bg-bg-tertiary/60 px-3 py-2 text-xs">
      <span className="shrink-0 font-medium text-text-secondary">{label}:</span>
      <span className={`min-w-0 break-all text-text-secondary ${mono ? 'font-mono' : ''}`}>{value}</span>
    </div>
  )
}

// ─── Summary modal ────────────────────────────────────────────────────────────

function SummaryModal({ open, onClose, file, summary }) {
  const text =
    typeof summary === 'string'
      ? summary
      : summary?.summary
        || summary?.text
        || summary?.content
        || (summary ? JSON.stringify(summary, null, 2) : '')

  return (
    <Modal
      open={open}
      onOpenChange={(next) => { if (!next) onClose() }}
      title="Summary"
      size="lg"
    >
      {file?.filename ? (
        <p className="-mt-2 mb-3 truncate text-xs text-text-secondary">{file.filename}</p>
      ) : null}
      <div className="max-h-[60vh] overflow-y-auto scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent">
        <p className="whitespace-pre-wrap text-sm leading-relaxed text-text-secondary">
          {text || 'No summary available for this file.'}
        </p>
      </div>
    </Modal>
  )
}

export default function FilesTab() {
  const {
    files,
    loading,
    uploading,
    deletingFileIds,
    reingestingFileIds,
    recentUploads,
    reviewStatesByFileId,
    reviewCasesByFileId,
    reviewErrorsByFileId,
    summaryByFileId,
    summaryLoadingFileIds,
    activeSummaryFileId,
    activeReviewFileId,
    loadFiles,
    uploadFiles,
    deleteFile,
    rerunIngestion,
    openSummary,
    closeSummary,
    openReview,
    closeReview,
    submitReviewDecision,
  } = useFiles()

  const [dragActive, setDragActive] = useState(false)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [fileToDelete, setFileToDelete] = useState(null)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [activeAuditFileId, setActiveAuditFileId] = useState(null)
  const [auditState, setAuditState] = useState({
    events: [],
    nextCursor: null,
    loading: false,
    loadingMore: false,
    error: null,
  })

  const activeReviewFile = files.find((file) => file.file_id === activeReviewFileId) || null
  const activeSummaryFile = files.find((file) => file.file_id === activeSummaryFileId) || null
  const activeAuditFile = files.find((file) => file.file_id === activeAuditFileId) || null

  const stats = useMemo(() => {
    const totalFiles = files.length
    const processingCount = files.filter((file) => computeEffectiveStatus(file) === 'processing').length
    const awaitingReviewCount = files.filter((file) => computeEffectiveStatus(file) === 'awaiting_review').length
    const completedCount = files.filter((file) => computeEffectiveStatus(file) === 'complete').length
    const errorCount = files.filter((file) => computeEffectiveStatus(file) === 'error').length
    return {
      totalFiles,
      processingCount,
      awaitingReviewCount,
      completedCount,
      errorCount,
      progressPercent: totalFiles > 0 ? Math.round((completedCount / totalFiles) * 100) : 0,
    }
  }, [files])

  const visibleFiles = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase()
    return files.filter((file) => {
      const matchesQuery = !normalizedQuery
        || (file.filename || '').toLocaleLowerCase().includes(normalizedQuery)
        || (file.content_type || '').toLocaleLowerCase().includes(normalizedQuery)
      const matchesStatus = statusFilter === 'all' || computeEffectiveStatus(file) === statusFilter
      return matchesQuery && matchesStatus
    })
  }, [files, query, statusFilter])

  const handleFileUpload = async (filesToUpload) => {
    if (!filesToUpload?.length) return
    try {
      await uploadFiles(Array.from(filesToUpload))
      toast.success('Files uploaded', {
        description: `${filesToUpload.length} file(s) queued for processing.`,
      })
    } catch (error) {
      toast.error('Upload failed', { description: error?.message || 'Please try again.' })
    }
  }

  const handleInputUpload = async (event) => {
    const selectedFiles = Array.from(event.target.files || [])
    if (selectedFiles.length === 0) return
    await handleFileUpload(selectedFiles)
    event.target.value = ''
  }

  const handleDrag = useCallback((event) => {
    event.preventDefault()
    event.stopPropagation()
    setDragActive(event.type === 'dragenter' || event.type === 'dragover')
  }, [])

  const handleDrop = useCallback((event) => {
    event.preventDefault()
    event.stopPropagation()
    setDragActive(false)
    handleFileUpload(event.dataTransfer?.files)
  }, [])

  const handleDeleteClick = (file) => {
    setFileToDelete(file)
    setDeleteModalOpen(true)
  }

  const handleConfirmDelete = async () => {
    if (!fileToDelete) return
    try {
      await deleteFile(fileToDelete.file_id)
      toast.success('File deleted')
      setFileToDelete(null)
    } catch (error) {
      toast.error('Delete failed', { description: error?.message || 'Please try again.' })
    }
  }

  const handleOpenReview = async (fileId) => {
    try {
      await openReview(fileId)
    } catch (error) {
      toast.error('Review case unavailable', { description: error?.message || 'Please try again.' })
    }
  }

  const handleOpenSummary = async (fileId) => {
    try {
      await openSummary(fileId)
    } catch (error) {
      toast.error('Summary unavailable', { description: error?.message || 'Please try again.' })
    }
  }

  const handleRerunIngestion = async (fileId) => {
    try {
      await rerunIngestion(fileId)
      toast.success('Re-ingestion started', { description: 'The file has been re-queued for processing.' })
    } catch (error) {
      toast.error('Re-ingestion failed', { description: error?.message || 'Please try again.' })
    }
  }

  const handleSubmitDecision = async (fileId, payload) => {
    try {
      await submitReviewDecision(fileId, payload)
      toast.success('Review decision submitted')
    } catch (error) {
      toast.error('Decision failed', { description: error?.message || 'Please try again.' })
      throw error
    }
  }

  const openAudit = useCallback(async (fileId) => {
    setActiveAuditFileId(fileId)
    setAuditState({
      events: [],
      nextCursor: null,
      loading: true,
      loadingMore: false,
      error: null,
    })

    try {
      const response = await fileService.getAuditTrail(fileId)
      setAuditState({
        events: Array.isArray(response?.events) ? response.events : [],
        nextCursor: response?.next_cursor || null,
        loading: false,
        loadingMore: false,
        error: null,
      })
    } catch (error) {
      setAuditState({
        events: [],
        nextCursor: null,
        loading: false,
        loadingMore: false,
        error: error?.message || 'Could not load the audit trail.',
      })
    }
  }, [])

  const loadMoreAudit = useCallback(async (fileId) => {
    if (!auditState.nextCursor || auditState.loadingMore) return

    setAuditState((current) => ({ ...current, loadingMore: true, error: null }))
    try {
      const response = await fileService.getAuditTrail(fileId, { cursor: auditState.nextCursor })
      setAuditState((current) => ({
        ...current,
        events: [...current.events, ...(Array.isArray(response?.events) ? response.events : [])],
        nextCursor: response?.next_cursor || null,
        loadingMore: false,
      }))
    } catch (error) {
      setAuditState((current) => ({
        ...current,
        loadingMore: false,
        error: error?.message || 'Could not load more audit events.',
      }))
    }
  }, [auditState.loadingMore, auditState.nextCursor])

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-[1600px] flex-col overflow-y-auto p-3 md:p-6">
      <PageHeader
        title="Knowledge files"
        description="Upload documents, follow ingestion progress, and review anything that needs attention."
        icon={FolderOpen}
        badge={<Badge variant="default">{stats.totalFiles} files</Badge>}
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={loadFiles}
              disabled={loading}
              leftIcon={<RefreshCw size={13} className={loading ? 'animate-spin' : ''} />}
            >
              Refresh
            </Button>
            <label
              role="button"
              aria-label={uploading ? 'Uploading files' : 'Upload files'}
              className={`inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium text-white transition-all duration-200 ${
                uploading
                  ? 'cursor-not-allowed bg-bg-tertiary text-text-muted opacity-60'
                  : 'bg-gradient-accent shadow-sm hover:-translate-y-px hover:shadow-glow'
              }`}
            >
              {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
              {uploading ? 'Uploading...' : 'Upload files'}
              <input type="file" multiple onChange={handleInputUpload} disabled={uploading} className="hidden" />
            </label>
          </div>
        }
      />

      <div className="flex min-h-0 flex-1 flex-col gap-4 xl:flex-row xl:overflow-hidden">
      {/* Main panel */}
      <div
        className="relative flex min-h-[560px] min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-border bg-bg-elevated shadow-sm xl:min-h-0"
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        {/* Drop target — claims space only while a drag is in progress */}
        <AnimatePresence>
          {dragActive ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.12 }}
              className="pointer-events-none absolute inset-2 z-20 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-primary bg-primary-soft backdrop-blur-sm"
            >
              <Upload size={26} className="text-primary" />
              <p className="mt-2 text-sm font-medium text-primary">Drop to upload</p>
              <p className="mt-1 text-[11px] text-text-secondary">PDF · DOCX · TXT · MD — up to 50 MB</p>
            </motion.div>
          ) : null}
        </AnimatePresence>

        {/* Header */}
        <div className="flex items-center gap-3 border-b border-border px-4 py-4 md:px-6">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-text-primary">Document library</h2>
              <Badge variant="default" size="xs">{visibleFiles.length} shown</Badge>
            </div>
            <p className="mt-0.5 text-xs text-text-secondary">
              Search, filter, and track every ingestion stage. Drag files here to upload.
            </p>
          </div>
          {/* Refresh indicator — visible only when refetching with existing data */}
          {loading && files.length > 0 ? (
            <div className="flex items-center gap-1.5 rounded-lg border border-border bg-bg-tertiary/60 px-2.5 py-1 text-[11px] text-text-secondary">
              <Loader2 size={11} className="animate-spin" />
              Refreshing
            </div>
          ) : null}
        </div>

        <div className="border-b border-border px-4 py-3 md:px-6">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by name or file type"
              icon={Search}
              size="sm"
              containerClassName="w-full lg:w-72"
            />
            <div
              role="group"
              aria-label="Filter files by status"
              className="flex min-w-0 flex-1 gap-1.5 overflow-x-auto pb-0.5 scrollbar-none"
            >
              {FILE_FILTERS.map((filter) => {
                const active = statusFilter === filter.id
                return (
                  <button
                    key={filter.id}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setStatusFilter(filter.id)}
                    className={`flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium transition-colors ${
                      active
                        ? 'border-border-focus bg-primary-soft text-primary'
                        : 'border-border bg-bg-muted text-text-secondary hover:text-text-primary'
                    }`}
                  >
                    {filter.label}
                    <span className="rounded-md bg-bg-elevated px-1.5 py-0.5 text-[11px] tabular-nums">
                      {stats[filter.countKey]}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        </div>

        {/* File list */}
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
          {/* Initial loading spinner — only when no cached data yet */}
          {loading && files.length === 0 ? (
            <div className="flex items-center gap-2 text-sm text-text-secondary">
              <Loader2 size={14} className="animate-spin" />
              Loading files…
            </div>
          ) : null}

          {/* Empty state — only after we know there truly are no files */}
          {!loading && files.length === 0 ? (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="flex min-h-[260px] flex-col items-center justify-center rounded-2xl border border-border bg-bg-tertiary/20 py-12"
            >
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-accent shadow-lg shadow-accent/20">
                <Upload className="text-white" size={28} />
              </div>
              <h3 className="mt-5 text-sm font-semibold text-text-primary">No files uploaded yet</h3>
              <p className="mt-1.5 max-w-xs text-center text-xs text-text-secondary">
                Upload a document to start the ingestion pipeline. Each stage is tracked individually.
              </p>
            </motion.div>
          ) : null}

          {!loading && files.length > 0 && visibleFiles.length === 0 ? (
            <div className="flex min-h-[240px] flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-bg-tertiary/20 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-soft text-primary">
                <Search size={19} />
              </span>
              <h3 className="mt-4 text-sm font-semibold text-text-primary">No matching documents</h3>
              <p className="mt-1 text-xs text-text-secondary">Try another search or choose a different status.</p>
              <button
                type="button"
                onClick={() => { setQuery(''); setStatusFilter('all') }}
                className="mt-3 text-xs font-medium text-primary hover:underline"
              >
                Clear filters
              </button>
            </div>
          ) : null}

          {visibleFiles.length > 0 ? (
            <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-3">
              <AnimatePresence mode="popLayout">
                {visibleFiles.map((file, index) => (
                  <FileCard
                    key={file.file_id || index}
                    file={file}
                    reviewState={reviewStatesByFileId[file.file_id] || 'no review'}
                    isDeleting={deletingFileIds.has(file.file_id)}
                    isReingesting={reingestingFileIds.has(file.file_id)}
                    isSummaryLoading={summaryLoadingFileIds.has(file.file_id)}
                    requiresReview={hasReviewPending(file)}
                    onDeleteClick={handleDeleteClick}
                    onOpenReview={handleOpenReview}
                    onOpenSummary={handleOpenSummary}
                    onRerunIngestion={handleRerunIngestion}
                    onOpenAudit={openAudit}
                  />
                ))}
              </AnimatePresence>
            </div>
          ) : null}
        </div>
      </div>

      {/* Sidebar */}
      <div className="grid w-full shrink-0 gap-4 md:grid-cols-2 xl:flex xl:w-[300px] xl:grid-cols-none xl:flex-col">
        {/* Readiness — the per-status counts live on the filter chips, not here */}
        <Card variant="elevated" className="p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-text-primary">Library readiness</div>
              <div className="mt-0.5 text-[11px] text-text-secondary">
                {stats.completedCount} of {stats.totalFiles} ready for retrieval
              </div>
            </div>
            {stats.totalFiles > 0 ? (
              <div
                className="relative h-12 w-12"
                role="img"
                aria-label={`${stats.progressPercent}% of documents ready for retrieval`}
              >
                <svg className="h-full w-full -rotate-90" viewBox="0 0 36 36">
                  <path
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none"
                    stroke="var(--border)"
                    strokeWidth="3.5"
                  />
                  <path
                    d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                    fill="none"
                    stroke="var(--success)"
                    strokeWidth="3.5"
                    strokeDasharray={`${stats.progressPercent}, 100`}
                    strokeLinecap="round"
                    className="transition-all duration-700"
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-[11px] font-bold tabular-nums text-success">{stats.progressPercent}%</span>
                </div>
              </div>
            ) : null}
          </div>
        </Card>

        {/* Recent uploads */}
        <Card variant="elevated" className="flex min-h-0 flex-1 flex-col p-5">
          <div className="mb-3">
            <div className="text-sm font-semibold text-text-primary">Latest activity</div>
            <div className="mt-0.5 text-[11px] text-text-secondary">Recent upload responses</div>
          </div>
          {recentUploads.length === 0 ? (
            <p className="text-xs text-text-secondary">Upload responses will appear here.</p>
          ) : (
            <div className="flex-1 min-h-0 space-y-2 overflow-y-auto">
              {recentUploads.map((upload) => (
                <div
                  key={`${upload.file_id}-${upload.uploadedAt}`}
                  className="rounded-xl border border-border bg-bg-tertiary/40 px-3 py-2.5"
                >
                  <div className="truncate text-xs font-semibold text-text-primary">{upload.filename}</div>
                  {/* The id returned by the upload call — the handle to quote
                      when asking an administrator about this file. */}
                  {upload.file_id ? (
                    <div className="mt-0.5 truncate font-mono text-[11px] text-text-secondary" title={upload.file_id}>
                      {upload.file_id}
                    </div>
                  ) : null}
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    <Badge variant={getFileStatusBadgeVariant(upload.status)} size="sm">
                      {getFileStatusLabel(upload.status)}
                    </Badge>
                    {upload.message ? <Badge variant="default" size="sm">{upload.message}</Badge> : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
      </div>

      <FileReviewDrawer
        open={Boolean(activeReviewFileId)}
        onOpenChange={(open) => { if (!open) closeReview() }}
        file={activeReviewFile}
        reviewCase={activeReviewFileId ? reviewCasesByFileId[activeReviewFileId] : null}
        reviewState={activeReviewFileId ? reviewStatesByFileId[activeReviewFileId] : 'no review'}
        reviewError={activeReviewFileId ? reviewErrorsByFileId[activeReviewFileId] : null}
        onSubmitDecision={handleSubmitDecision}
      />

      <SummaryModal
        open={Boolean(activeSummaryFileId)}
        onClose={closeSummary}
        file={activeSummaryFile}
        summary={activeSummaryFileId ? summaryByFileId[activeSummaryFileId] : null}
      />

      <AuditTrailPanel
        open={Boolean(activeAuditFileId)}
        onOpenChange={(open) => { if (!open) setActiveAuditFileId(null) }}
        file={activeAuditFile}
        auditState={auditState}
        onLoadMore={loadMoreAudit}
      />

      <ConfirmModal
        open={deleteModalOpen}
        onOpenChange={setDeleteModalOpen}
        title="Delete file?"
        description={fileToDelete ? `Delete "${fileToDelete.filename}"? This cannot be undone.` : ''}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={handleConfirmDelete}
        variant="danger"
        loading={fileToDelete ? deletingFileIds.has(fileToDelete.file_id) : false}
      />
    </div>
  )
}
