'use client'

import { Loader2, RefreshCw, Search, Trash2, Upload, X } from 'lucide-react'
import Input from '@/components/ui/Input'
import Select, { SelectItem } from '@/components/ui/Select'
import { useI18n } from '@/i18n'
import { SORT_OPTIONS, STATUS_FILTER_OPTIONS } from '../documentModel'

/**
 * One compact control strip: search, status, sort, and the result count.
 *
 * Deliberately not a filter panel — every control is a single row high, and
 * the count sits next to them so a narrowed list always says how narrow.
 */
export default function FilesToolbar({
  query,
  onQueryChange,
  status,
  onStatusChange,
  sort,
  onSortChange,
  direction,
  onDirectionToggle,
  counts,
  shownCount,
  totalCount,
  selectedCount,
  onClearSelection,
  onBulkDelete,
  bulkBusy,
  onRefresh,
  refreshing,
  uploading,
  onUpload,
}) {
  const { t } = useI18n()
  const statusOption = STATUS_FILTER_OPTIONS.find((option) => option.value === status)
  const sortOption = SORT_OPTIONS.find((option) => option.value === sort)
  const statusLabel = t(statusOption?.labelKey ?? 'knowledge.allStatuses')
  const sortLabel = t(sortOption?.labelKey ?? 'knowledge.sortUpdated')

  return (
    <div className="border-b border-border">
      <div className="flex flex-wrap items-center gap-2 px-4 py-3 md:px-5">
        <Input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={t('knowledge.searchDocuments')}
          aria-label={t('knowledge.searchDocuments')}
          // A search box accepts mixed text: a Hebrew reader may still be
          // looking for an English filename.
          dir="auto"
          icon={Search}
          size="sm"
          containerClassName="w-full sm:w-64"
        />

        <Select
          value={status}
          onValueChange={onStatusChange}
          className="h-8 w-auto min-w-[9.5rem] py-1 text-[13px]"
          aria-label={t('knowledge.filterByStatus')}
          valueLabel={statusLabel}
        >
          {STATUS_FILTER_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value} textValue={t(option.labelKey)}>
              <span className="flex w-full items-center justify-between gap-3 text-[13px]">
                {t(option.labelKey)}
                <span className="tabular-nums text-fg-soft">{counts[option.value] ?? 0}</span>
              </span>
            </SelectItem>
          ))}
        </Select>

        <Select
          value={sort}
          onValueChange={onSortChange}
          className="h-8 w-auto min-w-[7.5rem] py-1 text-[13px]"
          aria-label={t('knowledge.sortBy')}
          valueLabel={sortLabel}
        >
          {SORT_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value} textValue={t(option.labelKey)}>
              <span className="text-[13px]">{t(option.labelKey)}</span>
            </SelectItem>
          ))}
        </Select>

        <button
          type="button"
          onClick={onDirectionToggle}
          aria-label={t(direction === 'asc' ? 'knowledge.sortDescending' : 'knowledge.sortAscending')}
          className="h-8 rounded-lg border border-border px-2.5 text-[13px] text-fg-muted transition-colors hover:text-fg"
        >
          {t(direction === 'asc' ? 'knowledge.asc' : 'knowledge.desc')}
        </button>

        <p className="text-[13px] text-fg-soft" role="status" aria-live="polite">
          {shownCount === totalCount
            ? t('knowledge.documentCount', { count: totalCount })
            : t('knowledge.shownOfTotal', { shown: shownCount, total: totalCount })}
        </p>

        <div className="ms-auto flex items-center gap-2">
          <button
            type="button"
            onClick={onRefresh}
            disabled={refreshing}
            className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-border px-2.5 text-[13px] text-fg-muted transition-colors hover:text-fg disabled:opacity-50"
          >
            <RefreshCw size={13} className={refreshing ? 'animate-spin' : ''} aria-hidden="true" />
            {t('common.refresh')}
          </button>
          <label
            role="button"
            aria-label={t(uploading ? 'knowledge.uploadingDocuments' : 'knowledge.uploadDocuments')}
            className={`inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-lg px-3 text-[13px] font-medium text-[var(--primary-fg)] transition-colors ${
              uploading ? 'cursor-not-allowed bg-bg-tertiary text-fg-soft opacity-60' : 'bg-primary hover:bg-primary-hover'
            }`}
          >
            {uploading ? <Loader2 size={13} className="animate-spin" /> : <Upload size={13} />}
            {t(uploading ? 'upload.uploading' : 'upload.submit')}
            <input type="file" multiple onChange={onUpload} disabled={uploading} className="hidden" />
          </label>
        </div>
      </div>

      {/* Bulk bar — present only while a selection exists, and offering only
          delete, the one bulk-safe operation the files API supports. */}
      {selectedCount > 0 ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-border bg-primary-soft px-4 py-2 md:px-5">
          <span className="text-[13px] font-medium text-fg">
            {t('knowledge.selectedCount', { count: selectedCount })}
          </span>
          <button
            type="button"
            onClick={onBulkDelete}
            disabled={bulkBusy}
            className="inline-flex h-7 items-center gap-1.5 rounded-lg border border-border bg-bg-elevated px-2.5 text-[13px] text-danger transition-colors hover:bg-danger-soft disabled:opacity-50"
          >
            <Trash2 size={12} aria-hidden="true" />
            {t('common.delete')}
          </button>
          <button
            type="button"
            onClick={onClearSelection}
            className="ms-auto inline-flex h-7 items-center gap-1 rounded-lg px-2 text-[13px] text-fg-soft hover:text-fg"
          >
            <X size={12} aria-hidden="true" />
            {t('common.clear')}
          </button>
        </div>
      ) : null}
    </div>
  )
}
