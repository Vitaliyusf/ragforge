'use client'

import { ThumbsDown, ThumbsUp } from 'lucide-react'

/**
 * Answer feedback, compact enough to live under every answer.
 *
 * The previous version was a bordered panel with two feedback categories and a
 * free-text note, which dominated the answer it was rating. Flow feedback moved
 * to the Developer Inspector, where judging the pipeline belongs.
 */

const ANSWER_RATINGS = [
  { key: 'helpful', icon: ThumbsUp, label: 'Helpful', payload: { label: 'helpful', rating: 'positive' } },
  { key: 'not_helpful', icon: ThumbsDown, label: 'Not helpful', payload: { label: 'not_helpful', rating: 'negative' } },
]

export default function FeedbackControls({ turnId, feedback, onAnswerFeedback }) {
  if (!turnId || !onAnswerFeedback) return null

  const state = feedback?.answer
  const chosen = state?.status === 'sent' ? state.payload?.label : null
  const disabled = state?.status === 'sending'

  return (
    <div className="mt-1.5 flex items-center gap-1">
      {ANSWER_RATINGS.map(({ key, icon: Icon, label, payload }) => {
        const isChosen = chosen === key
        return (
          <button
            key={key}
            type="button"
            aria-label={label}
            aria-pressed={isChosen}
            disabled={disabled}
            onClick={() => onAnswerFeedback(turnId, payload)}
            className="rounded-lg p-1.5 text-[var(--fg-soft)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--fg)] disabled:opacity-50 focus-visible:outline-hidden focus-visible:ring-2"
            style={isChosen ? { color: 'var(--primary)' } : undefined}
          >
            <Icon size={14} />
          </button>
        )
      })}
      {state?.status === 'error' ? (
        <span className="text-xs text-[var(--danger)]">{state.error || 'Feedback failed'}</span>
      ) : null}
      {state?.status === 'sent' ? (
        <span className="text-xs text-[var(--fg-soft)]">Thanks for the feedback</span>
      ) : null}
    </div>
  )
}
