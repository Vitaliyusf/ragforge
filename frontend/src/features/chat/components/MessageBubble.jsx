'use client'

import React, { useMemo } from 'react'
import { motion } from 'framer-motion'
import { Copy, Info, Sparkles } from 'lucide-react'
import { formatMessageTime } from '@/lib/formatting/datetime'
import { bidiTextProps } from '@/lib/accessibility/direction'
import { buildAnswerQuality } from '@/features/chat/utils/answerQuality'
import AnswerQualitySummary from './AnswerQualitySummary'
import AnswerSources from './AnswerSources'
import FeedbackControls from './FeedbackControls'
import MarkdownContent from './MarkdownContent'
import TypingDots from './TypingDots'

// Safety-net: strip prompt echo in case backend hasn't cleaned it yet
function extractAnswer(text) {
  const echoAt = text.search(/\n+(?:System:|User:)/)
  const clean = echoAt === -1 ? text : text.slice(0, echoAt)
  return clean.replace(/^Answer:\s*/i, '').trim()
}

/** A quiet icon button for the answer footer. */
function IconAction({ label, icon: Icon, onClick }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="rounded-lg p-1.5 text-[var(--fg-soft)] opacity-80 transition-colors hover:bg-[var(--surface-hover)] hover:text-[var(--fg)] hover:opacity-100 focus-visible:outline-hidden focus-visible:ring-2"
    >
      <Icon size={14} />
    </button>
  )
}

/**
 * One message.
 *
 * The answer is the page: assistant prose sits directly on the surface at
 * reading size, with no bubble competing for attention, while the reader's own
 * message stays a small tinted card. Everything the answer is *about* —
 * sources, quality, feedback, the actions — is one quiet footer beneath it.
 * Identifiers, prompts, model slugs and evaluator payloads are deliberately
 * absent; they belong to the Developer Inspector behind the info control.
 */
const MessageBubble = React.memo(function MessageBubble({
  message,
  turn,
  onCopy,
  onOpenInspector,
  canInspect,
  onAnswerFeedback,
}) {
  const isUser = message.sender === 'You' || message.sender === 'User'
  const isStreaming = Boolean(message.isLoading)
  const rawText = (message.text || '').trimStart()
  const answer = isUser ? rawText : extractAnswer(rawText)

  const metadata = message.metadata || {}
  const review = metadata.answerReview || turn?.answerReview || null
  const sources = metadata.sources || turn?.sources || null
  const retrievalSummary = metadata.retrievalSummary || turn?.retrievalSummary || null
  const turnId = message.turnId || metadata.turnId || null
  const feedback = metadata.feedback || turn?.feedback || null

  // Quality is only meaningful once the answer has finished arriving.
  const quality = useMemo(
    () => (isUser || isStreaming ? null : buildAnswerQuality({ review, sources, retrievalSummary })),
    [isUser, isStreaming, review, sources, retrievalSummary]
  )

  const bidi = bidiTextProps(answer)
  const time = message.timestamp ? formatMessageTime(message.timestamp) : null

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
        className="flex flex-col items-end"
      >
        <div
          dir={bidi.dir}
          className={`max-w-[76%] whitespace-pre-wrap break-words rounded-2xl rounded-tr-md px-3.5 py-2.5 text-[14.5px] leading-relaxed ${bidi.className}`}
          style={{
            background: 'var(--primary-soft)',
            border: '1px solid var(--border)',
            color: 'var(--fg)',
            unicodeBidi: 'plaintext',
          }}
        >
          {answer}
        </div>
        <div className="mt-1 flex items-center gap-1.5 pe-1 text-xs text-[var(--fg-soft)]">
          <span>You</span>
          {time ? <span>{time}</span> : null}
          {canInspect ? (
            <IconAction label="Open developer inspector" icon={Info} onClick={() => onOpenInspector(message)} />
          ) : null}
        </div>
      </motion.div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="flex gap-3.5"
    >
      <div
        className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border"
        style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
      >
        <Sparkles size={15} className="text-primary" />
      </div>

      <div className="min-w-0 flex-1">
        <div className="mb-1.5 flex items-center gap-2 text-xs text-[var(--fg-soft)]">
          <span className="font-semibold text-[var(--fg-muted)]">{message.sender}</span>
          {time ? <span>{time}</span> : null}
        </div>

        {/* The answer itself: no card, no border — direction follows its text. */}
        <div
          dir={bidi.dir}
          className={`max-w-[68ch] break-words text-[15.5px] leading-[1.72] text-[var(--fg)] ${bidi.className}`}
          style={{ unicodeBidi: 'plaintext' }}
        >
          {!answer && isStreaming ? (
            <TypingDots />
          ) : (
            <MarkdownContent content={answer || (isStreaming ? '...' : '')} />
          )}
          {isStreaming && answer ? (
            <span className="ms-0.5 inline-block h-4 w-0.5 motion-safe:animate-blink align-middle bg-accent" />
          ) : null}
        </div>

        {!isStreaming ? (
          <>
            <AnswerSources sources={sources} />

            {/* One footer line: what the answer is worth, and what to do about it. */}
            <div
              className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-2"
              style={{ borderColor: 'var(--border)' }}
            >
              <AnswerQualitySummary quality={quality} />
              <span className="flex-1" aria-hidden="true" />
              <FeedbackControls
                turnId={turnId}
                feedback={feedback}
                onAnswerFeedback={onAnswerFeedback}
              />
              <div className="flex items-center gap-0.5">
                {answer ? <IconAction label="Copy answer" icon={Copy} onClick={() => onCopy(answer)} /> : null}
                {canInspect ? (
                  <IconAction label="Open developer inspector" icon={Info} onClick={() => onOpenInspector(message)} />
                ) : null}
              </div>
            </div>
          </>
        ) : null}
      </div>
    </motion.div>
  )
})

export default MessageBubble
