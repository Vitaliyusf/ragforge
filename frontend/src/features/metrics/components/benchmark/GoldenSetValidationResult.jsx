import { AlertTriangle, CheckCircle2 } from 'lucide-react'

export default function GoldenSetValidationResult({ result, error }) {
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
        <span>{result.valid ? 'Golden Set is valid' : 'Golden Set needs changes'}</span>
      </div>
      <p className="mt-1 tabular-nums">
        {validItems} valid · {invalidItems} invalid · {result.total_items || 0} total
      </p>
      {result.errors?.length > 0 && (
        <ul className="mt-2 list-disc space-y-1 pl-5">
          {result.errors.map((entry, index) => (
            <li key={`${entry.item_index ?? 'document'}-${index}`}>{entry.message}</li>
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
