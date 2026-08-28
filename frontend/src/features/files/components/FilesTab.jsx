'use client'

import { useCallback, useMemo, useState } from 'react'
import { ChevronLeft, ChevronRight, FolderOpen, Loader2, Search, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { useFiles } from '@/features/files'
import { ACTIVITY_FEATURES, useLiveActivitySource } from '@/features/activity'
import Badge from '@/components/ui/Badge'
import PageHeader from '@/components/ui/PageHeader'
import { ConfirmModal } from '@/components/ui/Modal'
import EmptyState from '@/components/feedback/EmptyState'
import { hasReviewPending } from '@/features/files/fileStatus'
import { countByStatus, selectDocuments } from '@/features/files/documentModel'
import { useDocumentActivity } from '@/features/files/hooks/useDocumentActivity'
import FileReviewDrawer from './FileReviewDrawer'
import DocumentTable from './DocumentTable'
import DocumentDrawer from './DocumentDrawer'
import FilesToolbar from './FilesToolbar'

/** How many documents a bulk action acts on at once. */
const BULK_CONCURRENCY = 4

/**
 * Rows rendered at a time.
 *
 * Filtering and sorting a thousand documents costs under a millisecond, so
 * the list itself never needed help. Mounting a thousand rows is what costs:
 * ~1.4s in jsdom against ~0.2s for a hundred. Paging is the cheaper answer
 * than virtualisation here — it is a slice and two buttons, it keeps the rows
 * ordinary table rows, and it adds no dependency.
 */
const PAGE_SIZE = 50

/**
 * Run one operation over many ids with a bounded number in flight.
 *
 * Bulk here is orchestration of the existing per-document endpoints, not a
 * batch API — the files service has none, and inventing one is out of scope.
 * @returns {Promise<{succeeded: number, failed: number}>}
 */
async function runBulk(ids, operation, limit = BULK_CONCURRENCY) {
  const queue = [...ids]
  let succeeded = 0
  let failed = 0

  const worker = async () => {
    while (queue.length > 0) {
      const id = queue.shift()
      try {
        await operation(id)
        succeeded += 1
      } catch {
        failed += 1
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(limit, queue.length) }, worker))
  return { succeeded, failed }
}

export default function FilesTab() {
  // useFiles already refreshes the shared file list every few seconds, so the
  // nav's background poll stands down for as long as this tab is open.
  useLiveActivitySource(ACTIVITY_FEATURES.FILES)

  const {
    files,
    loading,
    uploading,
    deletingFileIds,
    reviewCasesByFileId,
    reviewStatesByFileId,
    reviewErrorsByFileId,
    activeReviewFileId,
    loadFiles,
    uploadFiles,
    deleteFile,
    notifyFilesChanged,
    openReview,
    closeReview,
    submitReviewDecision,
  } = useFiles()

  const { activity, loadActivity, loadMoreActivity, resetActivity } = useDocumentActivity()

  const [dragActive, setDragActive] = useState(false)
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [sort, setSort] = useState('updated')
  const [direction, setDirection] = useState('desc')
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const [activeFileId, setActiveFileId] = useState(null)
  const [pendingDelete, setPendingDelete] = useState(null)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [page, setPage] = useState(1)

  const counts = useMemo(() => countByStatus(files), [files])
  const documents = useMemo(
    () => selectDocuments(files, { query, status: statusFilter, sort, direction }),
    [files, query, statusFilter, sort, direction]
  )
  const pageCount = Math.max(1, Math.ceil(documents.length / PAGE_SIZE))
  // Clamped rather than corrected in an effect: the list shrinks under the
  // reader whenever a poll lands, and a page that no longer exists should
  // simply show the last one that does.
  const currentPage = Math.min(page, pageCount)
  const pageStart = (currentPage - 1) * PAGE_SIZE
  const pageDocuments = useMemo(
    () => documents.slice(pageStart, pageStart + PAGE_SIZE),
    [documents, pageStart]
  )

  const reviewPendingIds = useMemo(
    () => new Set(files.filter(hasReviewPending).map((file) => file.file_id)),
    [files]
  )

  const activeFile = activeFileId ? files.find((file) => file.file_id === activeFileId) || null : null
  const activeReviewFile = files.find((file) => file.file_id === activeReviewFileId) || null

  const changeQuery = useCallback((value) => { setQuery(value); setPage(1) }, [])
  const changeStatus = useCallback((value) => { setStatusFilter(value); setPage(1) }, [])

  const handleSortChange = useCallback((nextSort) => {
    setPage(1)
    setSort((currentSort) => {
      if (currentSort === nextSort) {
        setDirection((currentDirection) => (currentDirection === 'asc' ? 'desc' : 'asc'))
        return currentSort
      }
      setDirection('desc')
      return nextSort
    })
  }, [])

  const handleUpload = useCallback(async (filesToUpload) => {
    if (!filesToUpload?.length) return
    try {
      await uploadFiles(Array.from(filesToUpload))
      toast.success('Upload accepted', {
        description: `${filesToUpload.length} document(s) queued for ingestion.`,
      })
    } catch (error) {
      toast.error('Upload failed', { description: error?.message || 'Please try again.' })
    }
  }, [uploadFiles])

  const handleInputUpload = useCallback(async (event) => {
    const selectedFiles = Array.from(event.target.files || [])
    if (selectedFiles.length === 0) return
    await handleUpload(selectedFiles)
    event.target.value = ''
  }, [handleUpload])

  const handleDrag = useCallback((event) => {
    event.preventDefault()
    event.stopPropagation()
    setDragActive(event.type === 'dragenter' || event.type === 'dragover')
  }, [])

  const handleDrop = useCallback((event) => {
    event.preventDefault()
    event.stopPropagation()
    setDragActive(false)
    handleUpload(event.dataTransfer?.files)
  }, [handleUpload])

  const handleOpenDocument = useCallback((fileId) => {
    setActiveFileId(fileId)
    loadActivity(fileId)
  }, [loadActivity])

  const handleCloseDocument = useCallback(() => {
    setActiveFileId(null)
    resetActivity()
  }, [resetActivity])

  const handleSelectChange = useCallback((fileId, checked) => {
    setSelectedIds((current) => {
      const next = new Set(current)
      if (checked) next.add(fileId)
      else next.delete(fileId)
      return next
    })
  }, [])

  const handleSelectAll = useCallback((checked) => {
    setSelectedIds(checked ? new Set(pageDocuments.map((file) => file.file_id)) : new Set())
  }, [pageDocuments])

  const clearSelection = useCallback(() => setSelectedIds(new Set()), [])

  const handleOpenReview = useCallback(async (fileId) => {
    try {
      await openReview(fileId)
    } catch (error) {
      toast.error('Review case unavailable', { description: error?.message || 'Please try again.' })
    }
  }, [openReview])

  const handleSubmitDecision = useCallback(async (fileId, payload) => {
    try {
      await submitReviewDecision(fileId, payload)
      toast.success('Review decision submitted')
    } catch (error) {
      toast.error('Decision failed', { description: error?.message || 'Please try again.' })
      throw error
    }
  }, [submitReviewDecision])

  // Delete — single row or selection — always passes through one confirmation.
  const requestDelete = useCallback((file) => setPendingDelete({ files: [file] }), [])
  const requestBulkDelete = useCallback(() => {
    const selected = files.filter((file) => selectedIds.has(file.file_id))
    if (selected.length > 0) setPendingDelete({ files: selected })
  }, [files, selectedIds])

  const confirmDelete = useCallback(async () => {
    const targets = pendingDelete?.files || []
    if (targets.length === 0) return
    setBulkBusy(true)
    try {
      // Every delete suppresses its own refresh: N deletes used to mean N list
      // reloads and N global change signals. The batch pays for one of each,
      // after it settles.
      const { succeeded, failed } = await runBulk(
        targets.map((file) => file.file_id),
        (fileId) => deleteFile(fileId, { refresh: false })
      )
      if (succeeded > 0) notifyFilesChanged()
      await loadFiles()
      if (targets.some((file) => file.file_id === activeFileId)) handleCloseDocument()
      setSelectedIds(new Set())
      if (failed > 0) {
        toast.error('Some documents were not deleted', {
          description: `${succeeded} deleted, ${failed} failed.`,
        })
      } else {
        toast.success(succeeded === 1 ? 'Document deleted' : `${succeeded} documents deleted`)
      }
    } finally {
      setBulkBusy(false)
      setPendingDelete(null)
    }
  }, [pendingDelete, deleteFile, notifyFilesChanged, loadFiles, activeFileId, handleCloseDocument])

  const deleteCount = pendingDelete?.files?.length || 0

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-[1600px] flex-col p-3 md:p-6">
      <PageHeader
        title="Documents"
        description="Every uploaded document, its ingestion state, and what to do about it."
        icon={FolderOpen}
        badge={<Badge variant="default">{files.length}</Badge>}
      />

      <div
        className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-border bg-bg-elevated shadow-sm"
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        {dragActive ? (
          <div className="pointer-events-none absolute inset-2 z-30 flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-primary bg-primary-soft backdrop-blur-xs">
            <Upload size={26} className="text-primary" />
            <p className="mt-2 text-[15px] font-medium text-primary">Drop to upload</p>
            <p className="mt-1 text-xs text-fg-muted">PDF · DOCX · TXT · MD — up to 50 MB</p>
          </div>
        ) : null}

        <FilesToolbar
          query={query}
          onQueryChange={changeQuery}
          status={statusFilter}
          onStatusChange={changeStatus}
          sort={sort}
          onSortChange={handleSortChange}
          direction={direction}
          onDirectionToggle={() => { setPage(1); setDirection((current) => (current === 'asc' ? 'desc' : 'asc')) }}
          counts={counts}
          shownCount={documents.length}
          totalCount={files.length}
          selectedCount={selectedIds.size}
          onClearSelection={clearSelection}
          onBulkDelete={requestBulkDelete}
          bulkBusy={bulkBusy}
          onRefresh={loadFiles}
          refreshing={loading}
          uploading={uploading}
          onUpload={handleInputUpload}
        />

        <div className="min-h-0 flex-1 overflow-y-auto">
          {loading && files.length === 0 ? (
            <p className="flex items-center gap-2 px-5 py-6 text-[15px] text-fg-muted">
              <Loader2 size={14} className="animate-spin" />
              Loading documents…
            </p>
          ) : null}

          {!loading && files.length === 0 ? (
            <EmptyState
              icon={Upload}
              title="No documents yet"
              description="Upload a document to start the ingestion pipeline. Each stage is tracked individually."
            />
          ) : null}

          {files.length > 0 && documents.length === 0 ? (
            <EmptyState
              icon={Search}
              size="sm"
              title="No matching documents"
              description="Try another search term or a different status."
              action={
                <button
                  type="button"
                  onClick={() => { setQuery(''); setStatusFilter('all'); setPage(1) }}
                  className="text-[13px] font-medium text-primary hover:underline"
                >
                  Clear filters
                </button>
              }
            />
          ) : null}

          {documents.length > 0 ? (
            <DocumentTable
              documents={pageDocuments}
              sort={sort}
              direction={direction}
              onSortChange={handleSortChange}
              selectedIds={selectedIds}
              onSelectChange={handleSelectChange}
              onSelectAll={handleSelectAll}
              activeFileId={activeFileId}
              deletingFileIds={deletingFileIds}
              reviewPendingIds={reviewPendingIds}
              onOpen={handleOpenDocument}
              onDelete={requestDelete}
              onReview={handleOpenReview}
            />
          ) : null}
        </div>

        {pageCount > 1 ? (
          <nav
            aria-label="Document pages"
            className="flex items-center justify-between gap-3 border-t border-border px-4 py-2 md:px-5"
          >
            <p className="text-[13px] text-fg-soft" role="status" aria-live="polite">
              Showing {pageStart + 1}–{Math.min(pageStart + PAGE_SIZE, documents.length)} of {documents.length}
            </p>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setPage(currentPage - 1)}
                disabled={currentPage === 1}
                aria-label="Previous page"
                className="flex h-7 w-7 items-center justify-center rounded-lg border border-border text-fg-muted transition-colors hover:text-fg disabled:opacity-40"
              >
                <ChevronLeft size={14} />
              </button>
              <span className="px-1.5 text-[13px] tabular-nums text-fg-muted">
                Page {currentPage} of {pageCount}
              </span>
              <button
                type="button"
                onClick={() => setPage(currentPage + 1)}
                disabled={currentPage === pageCount}
                aria-label="Next page"
                className="flex h-7 w-7 items-center justify-center rounded-lg border border-border text-fg-muted transition-colors hover:text-fg disabled:opacity-40"
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </nav>
        ) : null}
      </div>

      <DocumentDrawer
        open={Boolean(activeFile)}
        onOpenChange={(next) => { if (!next) handleCloseDocument() }}
        file={activeFile}
        activity={activity}
        onLoadMoreActivity={loadMoreActivity}
        onDelete={requestDelete}
        onReview={handleOpenReview}
        isDeleting={activeFile ? deletingFileIds.has(activeFile.file_id) : false}
        requiresReview={activeFile ? reviewPendingIds.has(activeFile.file_id) : false}
      />

      <FileReviewDrawer
        open={Boolean(activeReviewFileId)}
        onOpenChange={(open) => { if (!open) closeReview() }}
        file={activeReviewFile}
        reviewCase={activeReviewFileId ? reviewCasesByFileId[activeReviewFileId] : null}
        reviewState={activeReviewFileId ? reviewStatesByFileId[activeReviewFileId] : 'no review'}
        reviewError={activeReviewFileId ? reviewErrorsByFileId[activeReviewFileId] : null}
        onSubmitDecision={handleSubmitDecision}
      />

      <ConfirmModal
        open={Boolean(pendingDelete)}
        onOpenChange={(next) => { if (!next) setPendingDelete(null) }}
        title={deleteCount > 1 ? `Delete ${deleteCount} documents?` : 'Delete this document?'}
        // The files service deletes the record and its chunks, and asks the
        // vector service to drop the vectors — so this is what it claims.
        description={
          deleteCount === 1
            ? `"${pendingDelete?.files[0]?.filename}" and its searchable index will be removed. This cannot be undone.`
            : `${deleteCount} documents and their searchable index entries will be removed. This cannot be undone.`
        }
        confirmLabel={deleteCount > 1 ? `Delete ${deleteCount}` : 'Delete'}
        cancelLabel="Cancel"
        onConfirm={confirmDelete}
        variant="danger"
        loading={bulkBusy}
      />
    </div>
  )
}
