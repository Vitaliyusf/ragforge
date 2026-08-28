'use client'

import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react'
import DocumentRow from './DocumentRow'

/**
 * Columns, in render order. `sort` names the key the header toggles; a column
 * without one is not sortable. `className` carries the responsive collapse:
 * on a narrow screen the secondary columns fold away and Document, Status and
 * Actions remain.
 */
const COLUMNS = [
  { key: 'document', label: 'Document', sort: 'name', className: '' },
  { key: 'type', label: 'Type / size', sort: 'size', className: 'hidden md:table-cell' },
  { key: 'status', label: 'Status', sort: 'status', className: '' },
  { key: 'pipeline', label: 'Pipeline', sort: null, className: 'hidden lg:table-cell' },
  { key: 'updated', label: 'Updated', sort: 'updated', className: 'hidden md:table-cell' },
]

function SortIcon({ active, direction }) {
  if (!active) return <ChevronsUpDown size={11} className="opacity-40" aria-hidden="true" />
  return direction === 'asc'
    ? <ArrowUp size={11} aria-hidden="true" />
    : <ArrowDown size={11} aria-hidden="true" />
}

/**
 * The operational document table.
 *
 * Plain semantic markup plus the sort state the toolbar owns — no table
 * library. Sorting and filtering are a single pass over an in-memory array
 * the list request already returned, which is the whole of what a library
 * would have provided here.
 */
export default function DocumentTable({
  documents,
  sort,
  direction,
  onSortChange,
  selectedIds,
  onSelectChange,
  onSelectAll,
  activeFileId,
  deletingFileIds,
  reingestingFileIds,
  reviewPendingIds,
  onOpen,
  onDelete,
  onReindex,
  onReview,
}) {
  const allSelected = documents.length > 0 && documents.every((file) => selectedIds.has(file.file_id))
  const someSelected = documents.some((file) => selectedIds.has(file.file_id))

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-start">
        <caption className="sr-only">
          Documents, sorted by {sort}, {direction === 'asc' ? 'ascending' : 'descending'}
        </caption>
        <thead className="sticky top-0 z-10 bg-bg-elevated">
          <tr className="border-b border-border">
            <th scope="col" className="w-9 px-3 py-2">
              <input
                type="checkbox"
                checked={allSelected}
                ref={(node) => { if (node) node.indeterminate = someSelected && !allSelected }}
                onChange={(event) => onSelectAll(event.target.checked)}
                aria-label="Select all documents on this page"
                className="h-3.5 w-3.5 cursor-pointer accent-[var(--primary)]"
              />
            </th>
            {COLUMNS.map((column) => {
              const active = column.sort && sort === column.sort
              return (
                <th
                  key={column.key}
                  scope="col"
                  aria-sort={active ? (direction === 'asc' ? 'ascending' : 'descending') : undefined}
                  className={`px-3 py-2 text-start text-[11px] font-semibold uppercase tracking-wide text-fg-soft ${column.className}`}
                >
                  {column.sort ? (
                    <button
                      type="button"
                      onClick={() => onSortChange(column.sort)}
                      className="inline-flex items-center gap-1 uppercase tracking-wide hover:text-fg"
                    >
                      {column.label}
                      <SortIcon active={active} direction={direction} />
                    </button>
                  ) : (
                    column.label
                  )}
                </th>
              )
            })}
            <th scope="col" className="px-3 py-2 text-end text-[11px] font-semibold uppercase tracking-wide text-fg-soft">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {documents.map((file) => (
            <DocumentRow
              key={file.file_id}
              file={file}
              selected={selectedIds.has(file.file_id)}
              isActive={activeFileId === file.file_id}
              isDeleting={deletingFileIds.has(file.file_id)}
              isReingesting={reingestingFileIds.has(file.file_id)}
              requiresReview={reviewPendingIds.has(file.file_id)}
              onOpen={onOpen}
              onSelectChange={onSelectChange}
              onDelete={onDelete}
              onReindex={onReindex}
              onReview={onReview}
            />
          ))}
        </tbody>
      </table>
    </div>
  )
}
