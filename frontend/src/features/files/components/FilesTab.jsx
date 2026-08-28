'use client'

import { useCallback, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { FolderOpen, Loader2, RefreshCw, Search, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { useFiles } from '@/features/files'
import { ACTIVITY_FEATURES, useLiveActivitySource } from '@/features/activity'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import Badge from '@/components/ui/Badge'
import Input from '@/components/ui/Input'
import PageHeader from '@/components/ui/PageHeader'
import { ConfirmModal } from '@/components/ui/Modal'
import FileReviewDrawer from './FileReviewDrawer'
import AuditTrailPanel from './AuditTrailPanel'
import fileService from '@/features/files/services/fileService'
import FileCard from './FileCard'
import SummaryModal from './SummaryModal'
import EmptyState from '@/components/feedback/EmptyState'
import {
  computeEffectiveStatus,
  getFileStatusLabel,
  getFileStatusTone,
  hasReviewPending,
} from '@/features/files/fileStatus'

const FILE_FILTERS = [
  { id: 'all', label: 'All files', countKey: 'totalFiles' },
  { id: 'processing', label: 'Processing', countKey: 'processingCount' },
  { id: 'awaiting_review', label: 'Needs review', countKey: 'awaitingReviewCount' },
  { id: 'complete', label: 'Ready', countKey: 'completedCount' },
  { id: 'error', label: 'Errors', countKey: 'errorCount' },
]

export default function FilesTab() {
  // useFiles already refreshes the shared file list every few seconds, so the
  // nav's background poll stands down for as long as this tab is open.
  useLiveActivitySource(ACTIVITY_FEATURES.FILES)

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
              className={`inline-flex min-h-8 cursor-pointer items-center gap-1.5 rounded-lg px-3 py-1.5 text-[13px] font-medium text-[var(--primary-fg)] transition-colors duration-150 ${
                uploading
                  ? 'cursor-not-allowed bg-bg-tertiary text-text-muted opacity-60'
                  : 'bg-primary shadow-sm hover:bg-primary-hover'
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
              className="pointer-events-none absolute inset-2 z-20 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-primary bg-primary-soft backdrop-blur-xs"
            >
              <Upload size={26} className="text-primary" />
              <p className="mt-2 text-[15px] font-medium text-primary">Drop to upload</p>
              <p className="mt-1 text-xs text-text-secondary">PDF · DOCX · TXT · MD — up to 50 MB</p>
            </motion.div>
          ) : null}
        </AnimatePresence>

        {/* Header */}
        <div className="flex items-center gap-3 border-b border-border px-4 py-4 md:px-6">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-text-primary">Document library</h2>
              <Badge variant="default" size="xs">{visibleFiles.length} shown</Badge>
            </div>
            <p className="mt-0.5 text-[13px] text-text-secondary">
              Search, filter, and track every ingestion stage. Drag files here to upload.
            </p>
          </div>
          {/* Refresh indicator — visible only when refetching with existing data */}
          {loading && files.length > 0 ? (
            <div className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1 text-xs text-text-secondary">
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
                    className={`flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors ${
                      active
                        ? 'border-border-focus bg-primary-soft text-primary'
                        : 'border-border bg-bg-muted text-text-secondary hover:text-text-primary'
                    }`}
                  >
                    {filter.label}
                    <span className="rounded-md bg-bg-elevated px-1.5 py-0.5 text-xs tabular-nums">
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
            <div className="flex items-center gap-2 text-[15px] text-text-secondary">
              <Loader2 size={14} className="animate-spin" />
              Loading files…
            </div>
          ) : null}

          {/* Empty state — only after we know there truly are no files */}
          {!loading && files.length === 0 ? (
            <div className="rounded-2xl border border-border">
              <EmptyState
                icon={Upload}
                title="No files uploaded yet"
                description="Upload a document to start the ingestion pipeline. Each stage is tracked individually."
              />
            </div>
          ) : null}

          {!loading && files.length > 0 && visibleFiles.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border">
              <EmptyState
                icon={Search}
                size="sm"
                title="No matching documents"
                description="Try another search or choose a different status."
                action={
                  <button
                    type="button"
                    onClick={() => { setQuery(''); setStatusFilter('all') }}
                    className="text-[13px] font-medium text-primary hover:underline"
                  >
                    Clear filters
                  </button>
                }
              />
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
              <div className="text-[15px] font-semibold text-text-primary">Library readiness</div>
              <div className="mt-0.5 text-xs text-text-secondary">
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
                  <span className="text-xs font-bold tabular-nums text-success">{stats.progressPercent}%</span>
                </div>
              </div>
            ) : null}
          </div>
        </Card>

        {/* Recent uploads */}
        <Card variant="elevated" className="flex min-h-0 flex-1 flex-col p-5">
          <div className="mb-3">
            <div className="text-[15px] font-semibold text-text-primary">Latest activity</div>
            <div className="mt-0.5 text-xs text-text-secondary">Recent upload responses</div>
          </div>
          {recentUploads.length === 0 ? (
            <p className="text-[13px] text-text-secondary">Upload responses will appear here.</p>
          ) : (
            <div className="flex-1 min-h-0 space-y-2 overflow-y-auto">
              {recentUploads.map((upload) => (
                <div
                  key={`${upload.file_id}-${upload.uploadedAt}`}
                  className="rounded-xl border border-border px-3 py-2.5"
                >
                  <div className="truncate text-[13px] font-semibold text-text-primary">{upload.filename}</div>
                  {/* The id returned by the upload call — the handle to quote
                      when asking an administrator about this file. */}
                  {upload.file_id ? (
                    <div className="mt-0.5 truncate font-mono text-xs text-text-secondary" title={upload.file_id}>
                      {upload.file_id}
                    </div>
                  ) : null}
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    <Badge variant={getFileStatusTone(upload.status)} size="sm">
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
