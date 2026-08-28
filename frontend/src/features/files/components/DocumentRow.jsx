'use client'

import { memo } from 'react'
import { File, FileSpreadsheet, FileText, Image, Loader2, ShieldAlert, Trash2 } from 'lucide-react'
import { formatFileSize } from '@/lib/formatting/bytes'
import { formatAbsoluteDateTime, formatRelativeTime } from '@/lib/formatting/datetime'
import { DOCUMENT_STATUSES, getDocumentStatus, getDocumentType } from '../documentModel'
import { DocumentPipelineCell, DocumentStatusBadge } from './DocumentStatus'

function getFileTypeIcon(contentType, filename) {
  const type = String(contentType || '').toLowerCase()
  const extension = String(filename || '').split('.').pop()?.toLowerCase()
  if (type.startsWith('image/') || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(extension)) return Image
  if (['xlsx', 'xls', 'csv'].includes(extension) || type.includes('spreadsheet')) return FileSpreadsheet
  if (type.includes('pdf') || type.startsWith('text/') || ['pdf', 'txt', 'md', 'doc', 'docx'].includes(extension)) {
    return FileText
  }
  return File
}

const ACTION_BUTTON =
  'flex h-7 w-7 items-center justify-center rounded-lg text-fg-soft transition-colors hover:bg-surface-hover hover:text-fg disabled:opacity-40 disabled:hover:bg-transparent'

/**
 * One document, one row.
 *
 * Everything the row shows comes from the list request; opening the drawer is
 * what costs a detail fetch, never rendering a row.
 */
function DocumentRow({
  file,
  selected,
  isActive,
  isDeleting,
  requiresReview,
  onOpen,
  onSelectChange,
  onDelete,
  onReview,
}) {
  const Icon = getFileTypeIcon(file.content_type, file.filename)
  const status = getDocumentStatus(file)
  const type = getDocumentType(file)
  const updated = file.updated_at || file.created_at
  const relative = formatRelativeTime(updated)
  const failed = status === DOCUMENT_STATUSES.FAILED

  return (
    <tr
      onClick={() => onOpen(file.file_id)}
      data-testid="document-row"
      data-status={status}
      aria-selected={isActive || undefined}
      className={`cursor-pointer border-b border-border transition-colors last:border-b-0 ${
        isActive ? 'bg-primary-soft' : 'hover:bg-surface-hover'
      } ${isDeleting ? 'opacity-50' : ''}`}
    >
      <td className="w-9 px-3 py-2.5" onClick={(event) => event.stopPropagation()}>
        <input
          type="checkbox"
          checked={selected}
          onChange={(event) => onSelectChange(file.file_id, event.target.checked)}
          aria-label={`Select ${file.filename || 'document'}`}
          className="h-3.5 w-3.5 cursor-pointer accent-[var(--primary)]"
        />
      </td>

      <td className="min-w-0 px-3 py-2.5">
        <div className="flex items-center gap-2.5">
          <Icon size={15} className={`shrink-0 ${failed ? 'text-danger' : 'text-fg-soft'}`} aria-hidden="true" />
          <button
            type="button"
            onClick={(event) => { event.stopPropagation(); onOpen(file.file_id) }}
            // The full name is the accessible name and the hover title, so a
            // truncated one is never the only copy the reader can reach.
            title={file.filename || 'Unknown document'}
            dir="auto"
            className="block max-w-[38ch] truncate text-start text-[13px] font-medium text-fg hover:underline"
          >
            {file.filename || 'Unknown document'}
          </button>
        </div>
      </td>

      <td className="hidden whitespace-nowrap px-3 py-2.5 text-[13px] text-fg-soft md:table-cell">
        {[type, file.size ? formatFileSize(file.size) : null].filter(Boolean).join(' · ') || '—'}
      </td>

      <td className="px-3 py-2.5">
        <DocumentStatusBadge file={file} />
      </td>

      <td className="hidden px-3 py-2.5 lg:table-cell">
        <DocumentPipelineCell file={file} />
      </td>

      <td
        className="hidden whitespace-nowrap px-3 py-2.5 text-[13px] text-fg-soft md:table-cell"
        title={formatAbsoluteDateTime(updated) || undefined}
      >
        {relative || '—'}
      </td>

      <td className="px-3 py-2.5" onClick={(event) => event.stopPropagation()}>
        <div className="flex items-center justify-end gap-0.5">
          {requiresReview ? (
            <button
              type="button"
              onClick={() => onReview(file.file_id)}
              aria-label={`Review ${file.filename || 'document'}`}
              className={`${ACTION_BUTTON} text-warning hover:text-warning`}
            >
              <ShieldAlert size={14} />
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => onDelete(file)}
            disabled={isDeleting}
            aria-label={`Delete ${file.filename || 'document'}`}
            className={`${ACTION_BUTTON} hover:bg-danger-soft hover:text-danger`}
          >
            {isDeleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
          </button>
        </div>
      </td>
    </tr>
  )
}

/**
 * Memoised: the list refetches every five seconds, but a row only changes
 * when its own document or its own pending flags do. That is what keeps a
 * single row's status flip from re-rendering the other 999.
 */
export default memo(DocumentRow)
