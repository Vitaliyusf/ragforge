'use client'

import { ScoreBar, scoreColor, Empty } from './shared'

function QualityTab({ answerReview }) {
  if (!answerReview) {
    return <Empty label="No answer evaluation for this turn" />
  }

  const verdict = answerReview.verdict || 'unknown'
  const verdictColor = verdict === 'pass' ? 'var(--success)' : verdict === 'revise' ? 'var(--warning)' : verdict === 'unavailable' ? 'var(--fg-soft)' : 'var(--danger)'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-lg border border-border bg-bg-tertiary px-3 py-2.5">
        <span className="text-[13px] text-text-muted">Verdict</span>
        <span
          className="rounded-full px-2.5 py-0.5 text-[13px] font-semibold capitalize"
          style={{ backgroundColor: `${verdictColor}20`, color: verdictColor }}
        >
          {verdict}
        </span>
      </div>

      <div className="space-y-3">
        <ScoreBar
          label="Groundedness"
          value={answerReview.groundedness_score}
          color={scoreColor(answerReview.groundedness_score)}
        />
        <ScoreBar
          label="Completeness"
          value={answerReview.completeness_score}
          color={scoreColor(answerReview.completeness_score)}
        />
        <ScoreBar
          label="Safety"
          value={answerReview.safety_score}
          color={scoreColor(answerReview.safety_score)}
        />
      </div>

      {answerReview.issues?.length > 0 ? (
        <div>
          <div className="mb-1.5 text-[13px] font-medium text-text-muted">Issues</div>
          <div className="space-y-1">
            {answerReview.issues.map((issue, i) => (
              <div key={i} className="flex items-start gap-2 rounded-lg bg-bg-tertiary px-2.5 py-1.5 text-[13px] text-text-secondary">
                <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warning" />
                {issue}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="rounded-lg bg-bg-tertiary px-3 py-2 text-[13px] text-text-muted">No issues flagged</div>
      )}

      {answerReview.revision_applied ? (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-[13px] text-text-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          Answer was revised
        </div>
      ) : null}
    </div>
  )
}

export default QualityTab
