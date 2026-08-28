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

/**
 * One message.
 *
 * The default surface is answer → sources → feedback → compact quality state.
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

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={`flex gap-3.5 ${isUser ? 'flex-row-reverse' : ''}`}
    >
      {!isUser ? (
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border"
          style={{ borderColor: 'var(--border)' }}
        >
          <Sparkles size={16} className="text-primary" />
        </div>
      ) : null}

      <div className={`flex flex-col ${isUser ? 'max-w-[78%] items-end' : 'max-w-[88%] items-start'}`}>
        {/* Header row */}
        <div className={`mb-1 flex items-center gap-1.5 ${isUser ? 'flex-row-reverse' : ''}`}>
          <span className="text-xs font-semibold text-primary">{isUser ? 'You' : message.sender}</span>
          {message.timestamp ? (
            <span className="text-xs text-text-muted">{formatMessageTime(message.timestamp)}</span>
          ) : null}
          {canInspect ? (
            <button
              type="button"
              aria-label="Open developer inspector"
              onClick={() => onOpenInspector(message)}
              className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-bg-tertiary hover:text-primary focus-visible:outline-hidden focus-visible:ring-2"
            >
              <Info size={14} />
            </button>
          ) : null}
          {!isUser && answer ? (
            <button
              type="button"
              aria-label="Copy answer"
              onClick={() => onCopy(answer)}
              className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-bg-tertiary hover:text-primary focus-visible:outline-hidden focus-visible:ring-2"
            >
              <Copy size={14} />
            </button>
          ) : null}
        </div>

        {/* Answer bubble — direction follows the message's own text. */}
        <div
          dir={bidi.dir}
          className={`break-words px-4 py-3 text-[15px] leading-relaxed ${bidi.className} ${
            isUser
              ? 'rounded-2xl rounded-tr-md bg-primary text-[var(--primary-fg)] shadow-sm whitespace-pre-wrap'
              : 'rounded-2xl rounded-tl-md border border-border bg-bg-elevated text-text-secondary shadow-sm'
          }`}
          style={{ unicodeBidi: 'plaintext' }}
        >
          {!answer && isStreaming ? (
            <TypingDots />
          ) : isUser ? (
            answer
          ) : (
            <MarkdownContent content={answer || (isStreaming ? '...' : '')} />
          )}
          {isStreaming && answer ? (
            <span className="ms-0.5 inline-block h-4 w-0.5 motion-safe:animate-blink align-middle bg-accent" />
          ) : null}
        </div>

        {!isUser && !isStreaming ? (
          <>
            <AnswerSources sources={sources} />
            <FeedbackControls
              turnId={turnId}
              feedback={feedback}
              onAnswerFeedback={onAnswerFeedback}
            />
            <AnswerQualitySummary quality={quality} />
          </>
        ) : null}
      </div>
    </motion.div>
  )
})

export default MessageBubble
