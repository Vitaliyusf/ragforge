'use client'

import { GitBranch, MessageSquareWarning } from 'lucide-react'
import Button from '@/components/ui/Button'
import { DataCell } from '@/components/ui/DataDisplay'
import { formatAbsoluteDateTime } from '@/lib/formatting/datetime'
import { buildAnswerQuality } from '@/features/chat/utils/answerQuality'

/**
 * What this turn was and how it ended, in one screen.
 *
 * Flow feedback lives here rather than under the answer: judging whether the
 * pipeline behaved sensibly is an engineering question, and the reader of a
 * plain answer should not be asked it.
 */
export default function OverviewSection({
  mode,
  timestamp,
  answerLength,
  sources,
  retrievalSummary,
  review,
  turnId,
  feedback,
  onFlowFeedback,
}) {
  const quality = buildAnswerQuality({ review, sources, retrievalSummary })
  const answeredAt = formatAbsoluteDateTime(timestamp)
  const flowState = feedback?.flow

  const cells = [
    mode ? { label: 'Mode', value: mode === 'extended' ? 'Deep research' : 'Quick answer' } : null,
    answeredAt ? { label: 'Answered', value: answeredAt } : null,
    { label: 'Sources', value: quality.sourceCount },
    Number.isFinite(answerLength) ? { label: 'Answer length', value: `${answerLength} chars` } : null,
  ].filter(Boolean)

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-border bg-bg-tertiary px-3 py-2.5 text-[13px] text-text-secondary">
        {quality.kind === 'abstention'
          ? `Answerability: ${quality.answerability} · Decision: ${quality.decision}`
          : (quality.parts.join(' · ') || 'No quality signal was recorded for this turn.')}
      </div>

      <div className="grid grid-cols-2 gap-2">
        {cells.map((cell) => (
          <DataCell key={cell.label} reverse center label={cell.label} value={cell.value} />
        ))}
      </div>

      {turnId && onFlowFeedback ? (
        <div>
          <div className="mb-1.5 text-[13px] font-medium text-text-muted">Was this pipeline flow sensible?</div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={flowState?.status === 'sending'}
              onClick={() => onFlowFeedback(turnId, { category: 'flow_clear', label: 'clear' })}
              leftIcon={<GitBranch size={14} />}
            >
              Clear flow
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={flowState?.status === 'sending'}
              onClick={() => onFlowFeedback(turnId, { category: 'flow_confusing', label: 'confusing' })}
              leftIcon={<MessageSquareWarning size={14} />}
            >
              Confusing flow
            </Button>
            {flowState?.status === 'sent' ? (
              <span className="text-xs text-text-muted">Sent</span>
            ) : null}
            {flowState?.status === 'error' ? (
              <span className="text-xs text-[var(--danger)]">{flowState.error || 'Failed'}</span>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}
