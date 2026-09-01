'use client'

import { useCallback, useEffect, useRef } from 'react'
import { notifyError, notifySuccess } from '@/lib/notify'
import ActivityIndicator from './ActivityIndicator'
import ChatWelcome from './ChatWelcome'
import MessageBubble from './MessageBubble'

/**
 * The thread.
 *
 * This component owns scrolling and nothing else: a message renders itself, the
 * live execution state renders itself, and both are memoised so a long thread
 * does not re-render end to end on every streamed token.
 */
export default function MessageList({
  messages,
  turnsById,
  suggestedPrompts,
  onSuggestedPrompt,
  onOpenInspector,
  canInspect = false,
  onAnswerFeedback,
  activityStatus,
}) {
  const messagesEndRef = useRef(null)
  const prevLengthRef = useRef(0)

  useEffect(() => {
    if (messages.length > prevLengthRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
    prevLengthRef.current = messages.length
  }, [messages])

  const handleCopy = useCallback((text) => {
    // `writeText` rejects outside a secure context and when the permission
    // is denied. Swallowing that left the user believing they had copied.
    navigator.clipboard.writeText(text)
      .then(() => notifySuccess('Copied to clipboard'))
      .catch((error) => notifyError('Could not copy', {
        error,
        description: 'Your browser blocked clipboard access. Select the text and copy it manually.',
      }))
  }, [])

  return (
    <div
      className="min-h-0 flex-1 overflow-y-auto px-3 pb-3 pt-4 scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent md:px-6 md:pt-6"
      style={{ background: 'linear-gradient(180deg, var(--surface-hover) 0%, var(--surface) 38%)' }}
    >
      {messages.length === 0 ? (
        <ChatWelcome suggestedPrompts={suggestedPrompts} onSuggestedPrompt={onSuggestedPrompt} />
      ) : (
        <div className="mx-auto max-w-[64rem] space-y-7">
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              turn={message.turnId ? turnsById[message.turnId] : null}
              onCopy={handleCopy}
              onOpenInspector={onOpenInspector}
              canInspect={canInspect}
              onAnswerFeedback={onAnswerFeedback}
            />
          ))}
        </div>
      )}
      <ActivityIndicator status={activityStatus} />
      <div ref={messagesEndRef} />
    </div>
  )
}
