'use client'

import { useState } from 'react'
import { ThumbsDown, ThumbsUp } from 'lucide-react'

/**
 * Answer feedback, compact enough to live under every answer.
 *
 * The previous version was a bordered panel with two feedback categories and a
 * free-text note, which dominated the answer it was rating. Flow feedback moved
 * to the Developer Inspector, where judging the pipeline belongs.
 *
 * A rating is sent the moment it is clicked, so the signal is never lost while
 * someone decides whether to explain. The detail box appears only after a
 * negative rating — the one case where the reason is not already obvious — and
 * sending it emits a second `answer_feedback` over the same transport, with the
 * note in the `comment` field the backend already reads.
 */

const ANSWER_RATINGS = [
  { key: 'helpful', icon: ThumbsUp, label: 'Helpful', rating: 'positive' },
  { key: 'not_helpful', icon: ThumbsDown, label: 'Not helpful', rating: 'negative' },
]

export default function FeedbackControls({ turnId, feedback, onAnswerFeedback }) {
  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState('')
  const [detailSent, setDetailSent] = useState(false)

  if (!turnId || !onAnswerFeedback) return null

  const state = feedback?.answer
  const chosen = state?.status === 'sent' ? state.payload?.label : null
  const disabled = state?.status === 'sending'

  const rate = ({ key, rating }) => {
    onAnswerFeedback(turnId, { label: key, rating })
    setDetailOpen(key === 'not_helpful')
    if (key !== 'not_helpful') setDetailSent(false)
  }

  const sendDetail = (event) => {
    event.preventDefault()
    const comment = detail.trim()
    if (!comment) return
    onAnswerFeedback(turnId, { label: 'not_helpful', rating: 'negative', comment })
    setDetailSent(true)
    setDetailOpen(false)
    setDetail('')
  }

  return (
    <>
      <div className="flex items-center gap-0.5">
        {ANSWER_RATINGS.map((option) => {
          const Icon = option.icon
          const isChosen = chosen === option.key
          return (
            <button
              key={option.key}
              type="button"
              aria-label={option.label}
              title={option.label}
              aria-pressed={isChosen}
              disabled={disabled}
              onClick={() => rate(option)}
              className="rounded-lg p-1.5 text-[var(--fg-soft)] opacity-80 transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--fg)] hover:opacity-100 disabled:opacity-50 focus-visible:outline-hidden focus-visible:ring-2"
              style={isChosen ? { color: 'var(--primary)', opacity: 1 } : undefined}
            >
              <Icon size={14} />
            </button>
          )
        })}
        {state?.status === 'error' ? (
          <span className="ms-1 text-xs text-[var(--danger)]">{state.error || 'Feedback failed'}</span>
        ) : null}
        {state?.status === 'sent' && !detailOpen ? (
          <span className="ms-1 text-xs text-[var(--fg-soft)]">
            {detailSent ? 'Thanks — noted' : 'Thanks for the feedback'}
          </span>
        ) : null}
      </div>

      {detailOpen ? (
        <form onSubmit={sendDetail} className="order-last flex w-full items-center gap-2 pt-1.5">
          <input
            type="text"
            dir="auto"
            value={detail}
            onChange={(event) => setDetail(event.target.value)}
            aria-label="What was wrong with this answer? (optional)"
            placeholder="What was wrong? (optional)"
            className="min-w-0 flex-1 rounded-lg border px-2.5 py-1.5 text-[13px] text-[var(--fg)] outline-hidden focus-visible:ring-2"
            style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
          />
          <button
            type="submit"
            disabled={!detail.trim()}
            className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-[var(--fg-muted)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--fg)] disabled:opacity-40"
          >
            Send
          </button>
          <button
            type="button"
            onClick={() => { setDetailOpen(false); setDetail('') }}
            className="rounded-lg px-2 py-1.5 text-xs text-[var(--fg-soft)] transition-colors hover:text-[var(--fg)]"
          >
            Skip
          </button>
        </form>
      ) : null}
    </>
  )
}
