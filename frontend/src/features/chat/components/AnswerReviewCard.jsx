'use client'

import Badge from '@/components/ui/Badge'

function scoreTone(score) {
  if (score >= 0.85) return 'text-emerald-500'
  if (score >= 0.65) return 'text-amber-500'
  return 'text-red-500'
}

function verdictVariant(verdict) {
  if (verdict === 'pass') return 'success'
  if (verdict === 'revise') return 'warning'
  if (verdict === 'fail') return 'error'
  return 'default'
}

export default function AnswerReviewCard({ review }) {
  if (!review) return null

  const issues = Array.isArray(review.issues) ? review.issues : []

  return (
    <div className="mt-2 w-full rounded-2xl border border-border bg-bg-tertiary/70 p-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-text-muted">Answer Review</span>
        <Badge variant={verdictVariant(review.verdict)}>
          {String(review.verdict || 'unknown').replace(/_/g, ' ')}
        </Badge>
        {review.revision_applied ? (
          <Badge variant="accent">Revision applied</Badge>
        ) : (
          <Badge variant="default">Revision not applied</Badge>
        )}
      </div>

      {(review.model_name || review.created_at) ? (
        <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-text-muted">
          {review.model_name ? <span>Model: <span className="font-mono text-text-secondary">{review.model_name}</span></span> : null}
          {review.created_at ? <span>Created: {review.created_at}</span> : null}
        </div>
      ) : null}

      <div className="grid grid-cols-3 gap-2 text-xs">
        <Metric label="Groundedness" score={review.groundedness_score} />
        <Metric label="Completeness" score={review.completeness_score} />
        <Metric label="Safety" score={review.safety_score} />
      </div>

      <div className="mt-3">
        <div className="mb-1 text-xs font-medium text-text-muted">Issues</div>
        {issues.length > 0 ? (
          <ul className="space-y-1 text-xs text-text-secondary">
            {issues.map((issue, index) => (
              <li key={`${issue}-${index}`} className="rounded-xl border border-border bg-bg-elevated px-2.5 py-1.5">
                {issue}
              </li>
            ))}
          </ul>
        ) : (
          <div className="rounded-xl border border-border bg-bg-elevated px-2.5 py-1.5 text-xs text-text-secondary">
            No review issues were reported for this answer.
          </div>
        )}
      </div>
    </div>
  )
}

function Metric({ label, score }) {
  const value = Number.isFinite(score) ? Math.round(score * 100) : null

  return (
    <div className="rounded-xl border border-border bg-bg-elevated px-2.5 py-2">
      <div className="text-[11px] text-text-muted">{label}</div>
      <div className={`mt-1 text-sm font-semibold ${value == null ? 'text-text-secondary' : scoreTone(score)}`}>
        {value == null ? '-' : `${value}%`}
      </div>
    </div>
  )
}
