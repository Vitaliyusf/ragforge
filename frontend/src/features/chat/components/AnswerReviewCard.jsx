'use client'

import Badge from '@/components/ui/Badge'
import { DataCell } from '@/components/ui/DataDisplay'

function scoreTone(score) {
  if (score >= 0.85) return 'text-success'
  if (score >= 0.65) return 'text-warning'
  return 'text-danger'
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
        <span className="text-[13px] font-semibold uppercase tracking-wide text-text-muted">Answer Review</span>
        <Badge variant={verdictVariant(review.verdict)}>
          {String(review.verdict || 'unknown').replace(/_/g, ' ')}
        </Badge>
        {review.revision_applied ? (
          <Badge variant="accent">Revision applied</Badge>
        ) : (
          <Badge variant="default">Revision not applied</Badge>
        )}
      </div>

      {(review.review_id || review.model_name || review.created_at) ? (
        <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
          {review.review_id ? <span>Review: <span className="font-mono text-text-secondary">{review.review_id}</span></span> : null}
          {review.model_name ? <span>Model: <span className="font-mono text-text-secondary">{review.model_name}</span></span> : null}
          {review.created_at ? <span>Created: {review.created_at}</span> : null}
        </div>
      ) : null}

      <div className="grid grid-cols-3 gap-2 text-[13px]">
        <Metric label="Groundedness" score={review.groundedness_score} />
        <Metric label="Completeness" score={review.completeness_score} />
        <Metric label="Safety" score={review.safety_score} />
      </div>

      <div className="mt-3">
        <div className="mb-1 text-[13px] font-medium text-text-muted">Issues</div>
        {issues.length > 0 ? (
          <ul className="space-y-1 text-[13px] text-text-secondary">
            {issues.map((issue, index) => (
              <li key={`${issue}-${index}`} className="rounded-xl border border-border bg-bg-elevated px-2.5 py-1.5">
                {issue}
              </li>
            ))}
          </ul>
        ) : (
          <div className="rounded-xl border border-border bg-bg-elevated px-2.5 py-1.5 text-[13px] text-text-secondary">
            No review issues were reported for this answer.
          </div>
        )}
      </div>
    </div>
  )
}

/** Score-to-percentage presentation; the markup lives in DataCell. */
function Metric({ label, score }) {
  const value = Number.isFinite(score) ? Math.round(score * 100) : null

  return (
    <DataCell
      label={label}
      uppercaseLabel={false}
      value={value == null ? '-' : `${value}%`}
      valueClassName={`font-semibold ${value == null ? 'text-text-secondary' : scoreTone(score)}`}
    />
  )
}
