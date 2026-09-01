'use client'

import { useState } from 'react'
import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { useI18n } from '@/i18n'

/**
 * Answer feedback, compact enough to live under every answer.
 *
 * The previous version was a bordered panel with two feedback categories and a
 * free-text note, which dominated the answer it was rating. Flow feedback moved
 * to the Developer Inspector, where judging the pipeline belongs.
 *
 * One rating is one stored event. The backend persists every `answer_feedback`
 * independently and those events feed the memory threshold, so a single click
 * must never produce two negative signals.
 *
 * A positive rating is therefore sent on click. A negative one opens the
 * optional detail box first — the one case where the reason is not already
 * obvious — and the event is sent exactly once, when the reader either sends a
 * note (carried in the `comment` field the backend already reads) or skips it.
 */

// `key` and `rating` are the values the backend stores and never change with
// the interface language; only `labelKey` is what the reader sees.
const ANSWER_RATINGS = [
  { key: 'helpful', icon: ThumbsUp, labelKey: 'chat.feedbackHelpful', rating: 'positive' },
  { key: 'not_helpful', icon: ThumbsDown, labelKey: 'chat.feedbackNotHelpful', rating: 'negative' },
]

export default function FeedbackControls({ turnId, feedback, onAnswerFeedback }) {
  const { t } = useI18n()
  const [detailOpen, setDetailOpen] = useState(false)
  const [detail, setDetail] = useState('')
  const [detailSent, setDetailSent] = useState(false)

  if (!turnId || !onAnswerFeedback) return null

  const state = feedback?.answer
  const chosen = state?.status === 'sent' ? state.payload?.label : null
  const disabled = state?.status === 'sending'

  const rate = ({ key, rating }) => {
    // A negative rating waits for the reader's Send or Skip, so the turn
    // produces one feedback event rather than two.
    if (key === 'not_helpful') {
      setDetailOpen(true)
      return
    }
    onAnswerFeedback(turnId, { label: key, rating })
    setDetailOpen(false)
    setDetailSent(false)
  }

  const sendNegative = (comment) => {
    onAnswerFeedback(turnId, {
      label: 'not_helpful',
      rating: 'negative',
      ...(comment ? { comment } : {}),
    })
    setDetailSent(Boolean(comment))
    setDetailOpen(false)
    setDetail('')
  }

  const submitDetail = (event) => {
    event.preventDefault()
    sendNegative(detail.trim())
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
              aria-label={t(option.labelKey)}
              title={t(option.labelKey)}
              aria-pressed={option.key === 'not_helpful' ? isChosen || detailOpen : isChosen}
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
          <span className="ms-1 text-xs text-[var(--danger)]">
            {state.error || t('chat.feedbackFailed')}
          </span>
        ) : null}
        {state?.status === 'sent' && !detailOpen ? (
          <span className="ms-1 text-xs text-[var(--fg-soft)]">
            {detailSent ? t('chat.feedbackNoted') : t('chat.feedbackThanks')}
          </span>
        ) : null}
      </div>

      {detailOpen ? (
        <form onSubmit={submitDetail} className="order-last flex w-full items-center gap-2 pt-1.5">
          <input
            type="text"
            dir="auto"
            value={detail}
            onChange={(event) => setDetail(event.target.value)}
            aria-label={t('chat.feedbackDetailLabel')}
            placeholder={t('chat.feedbackDetailPlaceholder')}
            className="min-w-0 flex-1 rounded-lg border px-2.5 py-1.5 text-[13px] text-[var(--fg)] outline-hidden focus-visible:ring-2"
            style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
          />
          <button
            type="submit"
            disabled={!detail.trim() || disabled}
            className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-[var(--fg-muted)] transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--fg)] disabled:opacity-40"
          >
            {t('chat.feedbackSend')}
          </button>
          <button
            type="button"
            onClick={() => sendNegative('')}
            disabled={disabled}
            className="rounded-lg px-2 py-1.5 text-xs text-[var(--fg-soft)] transition-colors hover:text-[var(--fg)] disabled:opacity-40"
          >
            {t('chat.feedbackSkip')}
          </button>
        </form>
      ) : null}
    </>
  )
}
