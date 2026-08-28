'use client'

import { memo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  ChevronDown,
  File,
  FileText,
  History,
  Image,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Trash2,
} from 'lucide-react'
import Badge from '@/components/ui/Badge'
import StatusIndicator from '@/components/status/StatusIndicator'
import { DataRow } from '@/components/ui/DataDisplay'
import { formatFileSize } from '@/lib/formatting/bytes'
import {
  computeEffectiveStatus,
  getEffectiveStatusLabel,
  getEffectiveStatusTone,
} from '@/features/files/fileStatus'
import PipelineBar from './PipelineBar'

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
  const statusTone = getEffectiveStatusTone(file)
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
              <div className="truncate text-[15px] font-semibold text-text-primary">{file.filename || 'Unknown'}</div>
              <div className="mt-0.5 flex items-center gap-2">
                <span className="text-[13px] text-text-secondary">{formatFileSize(file.size)}</span>
                {file.content_type ? (
                  <>
                    <span className="text-text-muted">·</span>
                    <span className="truncate text-[13px] text-text-secondary">{file.content_type}</span>
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
        <StatusIndicator tone={statusTone} label={statusLabel} />
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
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium text-warning transition hover:bg-warning-soft"
          >
            <ShieldAlert size={13} />
            Review
          </button>
        ) : null}
        <button
          onClick={() => onOpenAudit(file.file_id)}
          aria-label="View Audit Trail"
          className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium text-text-secondary transition hover:bg-bg-tertiary hover:text-text-primary"
        >
          <History size={13} /> Audit
        </button>
        <button
          onClick={() => onOpenSummary(file.file_id)}
          disabled={isSummaryLoading}
          className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium text-text-secondary transition hover:bg-bg-tertiary hover:text-text-primary disabled:opacity-50"
        >
          {isSummaryLoading ? <Loader2 size={13} className="animate-spin" /> : <FileText size={13} />}
          Summary
        </button>
        <button
          onClick={() => onRerunIngestion(file.file_id)}
          disabled={isReingesting}
          className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] font-medium text-text-secondary transition hover:bg-bg-tertiary hover:text-text-primary disabled:opacity-50"
        >
          {isReingesting ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          Re-ingest
        </button>
        <button
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="ml-auto flex items-center gap-1 rounded-lg px-2 py-1.5 text-[13px] text-text-secondary transition hover:bg-bg-tertiary hover:text-text-primary"
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
                <DataRow label="Owner" value={file.owner_display_name || file.owner_email} />
              ) : null}
              <DataRow label="File ID" value={file.file_id} mono />
              {file.current_task_id ? (
                <DataRow label="Task ID" value={file.current_task_id} mono />
              ) : null}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </motion.div>
  )
}

/**
 * Memoised: the grid re-renders on every poll of the files list, but an
 * individual card only changes when its own file or pending flags change.
 */
export default memo(FileCard)
