import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { useI18n } from '@/i18n'

export default function GoldenSetValidationResult({ result, error }) {
  const { t } = useI18n()
  if (error) {
    return (
      <div role="alert" className="rounded-lg px-3 py-2 text-[13px]" style={dangerStyle}>
        <span className="flex items-center gap-2 font-medium">
          <AlertTriangle size={14} aria-hidden="true" />
          Validation could not be completed
        </span>
        <p className="mt-1">{error}</p>
      </div>
    )
  }

  if (!result) return null

  const validItems = result.valid_items || 0
  const invalidItems = result.invalid_items || 0
  const preparation = result.preparation

  return (
    <div
      role={result.valid ? 'status' : 'alert'}
      className="rounded-lg px-3 py-2 text-[13px]"
      style={result.valid ? successStyle : dangerStyle}
    >
      <div className="flex items-center gap-2 font-medium">
        {result.valid ? (
          <CheckCircle2 size={14} aria-hidden="true" />
        ) : (
          <AlertTriangle size={14} aria-hidden="true" />
        )}
        <span>{t(result.valid ? 'importer.valid' : 'importer.needsChanges')}</span>
      </div>
      <p className="mt-1 tabular-nums">
        {t('importer.itemCounts', {
          valid: validItems,
          invalid: invalidItems,
          total: result.total_items || 0,
        })}
      </p>
      {preparation && (
        <p className="mt-1 tabular-nums">
          {t('importer.preparationCounts', {
            ready: preparation.ready || 0,
            unresolved: preparation.unresolved || 0,
            ambiguous: preparation.ambiguous || 0,
            unanswerable: preparation.unanswerable || 0,
          })}
        </p>
      )}
      {preparation &&
        (preparation.chunk_ready ||
          preparation.file_fallback ||
          preparation.resolved_facts ||
          preparation.unresolved_facts ||
          preparation.unready_files) > 0 && (
          <p className="mt-1 tabular-nums">
            {t('importer.resolutionCounts', {
              chunkReady: preparation.chunk_ready || 0,
              fileFallback: preparation.file_fallback || 0,
              resolvedFacts: preparation.resolved_facts || 0,
              unresolvedFacts: preparation.unresolved_facts || 0,
              unreadyFiles: preparation.unready_files || 0,
            })}
          </p>
        )}
      {/* Validation messages are the server's own text. */}
      {result.errors?.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 ps-5">
          {result.errors.map((entry, index) => (
            <li key={`${entry.item_index ?? 'document'}-${index}`}>{entry.message}</li>
          ))}
        </ul>
      )}
      {result.warnings?.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 ps-5" style={{ color: 'var(--warning)' }}>
          {result.warnings.map((entry, index) => (
            <li key={`warning-${entry.item_index ?? 'document'}-${index}`}>{entry.message}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

const successStyle = {
  background: 'var(--success-soft)',
  border: '1px solid rgba(34,197,94,0.25)',
  color: 'var(--success)',
}

const dangerStyle = {
  background: 'var(--danger-soft)',
  border: '1px solid rgba(239,68,68,0.25)',
  color: 'var(--danger)',
}
