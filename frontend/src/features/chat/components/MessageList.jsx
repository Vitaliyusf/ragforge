'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ArrowUpRight, Bot, ChevronDown, ChevronUp, Copy, Info, Sparkles } from 'lucide-react'
import { toast } from 'sonner'
import { formatMessageTime } from '@/utils/common'
import { containsHebrew, getTextDirection } from '@/utils/textUtils'
import AnswerReviewCard from './AnswerReviewCard'
// import FeedbackControls from './FeedbackControls' // feedback UI temporarily hidden

// Safety-net: strip prompt echo in case backend hasn't cleaned it yet
function extractAnswer(text) {
  const echoAt = text.search(/\n+(?:System:|User:)/)
  const clean = echoAt === -1 ? text : text.slice(0, echoAt)
  return clean.replace(/^Answer:\s*/i, '').trim()
}

export default function MessageList({
  messages,
  turnsById,
  suggestedPrompts,
  onSuggestedPrompt,
  onOpenDebug,
  canViewDebug = false,
  onAnswerFeedback,
  onFlowFeedback,
  extendedProgress,
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
    navigator.clipboard.writeText(text).then(() => toast.success('Copied to clipboard'))
  }, [])

  return (
    <div
      className="min-h-0 flex-1 overflow-y-auto px-3 pb-3 pt-4 scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent md:px-6 md:pt-6"
      style={{ background: 'linear-gradient(180deg, var(--surface-hover) 0%, var(--surface) 38%)' }}
    >
      {messages.length === 0 ? (
        <EmptyState suggestedPrompts={suggestedPrompts} onSuggestedPrompt={onSuggestedPrompt} />
      ) : (
        <div className="mx-auto max-w-3xl space-y-6">
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              turn={message.turnId ? turnsById[message.turnId] : null}
              onCopy={handleCopy}
              onOpenDebug={onOpenDebug}
              canViewDebug={canViewDebug}
              onAnswerFeedback={onAnswerFeedback}
              onFlowFeedback={onFlowFeedback}
            />
          ))}
        </div>
      )}
      {extendedProgress ? (
        <div className="mx-auto max-w-3xl">
          <ExtendedProgressIndicator progress={extendedProgress} />
        </div>
      ) : null}
      <div ref={messagesEndRef} />
    </div>
  )
}

// ─── Message bubble ────────────────────────────────────────────────────────────

const MessageBubble = React.memo(function MessageBubble({
  message,
  turn,
  onCopy,
  onOpenDebug,
  canViewDebug,
  onAnswerFeedback,
  onFlowFeedback,
}) {
  const isUser      = message.sender === 'You' || message.sender === 'User'
  const isStreaming  = Boolean(message.isLoading)
  const rawText     = (message.text || '').trimStart()
  const answer      = isUser ? rawText : extractAnswer(rawText)
  const [expanded, setExpanded] = useState(false)

  const debugPayloads = message.metadata?.debugPayloads || turn?.debugPayloads || {}
  const systemPrompt  = debugPayloads.system_prompt || ''
  const rawPrompt     = debugPayloads.raw_prompt || ''
  const hasPromptData = canViewDebug && Boolean(systemPrompt || rawPrompt)

  const textDir  = getTextDirection(answer)
  const hasHebrew = containsHebrew(answer)
  const review    = message.metadata?.answerReview || turn?.answerReview

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
          style={{ background: 'var(--gradient-subtle)', borderColor: 'var(--border)' }}
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
          {canViewDebug ? (
            <button
              type="button"
              aria-label="View trace and debug details"
              onClick={() => onOpenDebug(message)}
              className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-bg-tertiary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
            >
              <Info size={14} />
            </button>
          ) : null}
          {!isUser && answer ? (
            <button
              type="button"
              aria-label="Copy answer"
              onClick={() => onCopy(answer)}
              className="rounded-lg p-1.5 text-text-muted transition-colors hover:bg-bg-tertiary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
            >
              <Copy size={14} />
            </button>
          ) : null}
        </div>

        {/* Answer bubble */}
        <div
          dir={hasHebrew ? textDir : 'ltr'}
          lang={hasHebrew ? 'he' : undefined}
          className={`break-words px-4 py-3 text-[15px] leading-relaxed ${
            isUser
              ? 'rounded-2xl rounded-tr-md bg-primary text-[var(--primary-fg)] shadow-sm whitespace-pre-wrap'
              : 'rounded-2xl rounded-tl-md border border-border bg-bg-elevated text-text-secondary shadow-sm'
          } ${hasHebrew && textDir === 'rtl' ? 'text-right' : 'text-left'}`}
          style={hasHebrew ? { unicodeBidi: 'plaintext' } : undefined}
        >
          {!answer && isStreaming ? (
            <TypingDots />
          ) : isUser ? (
            answer
          ) : (
            <MarkdownContent content={answer || (isStreaming ? '...' : '')} />
          )}
          {isStreaming && answer ? (
            <span className="ml-0.5 inline-block h-4 w-0.5 animate-blink align-middle bg-accent" />
          ) : null}
        </div>

        {/* Expand toggle — only for assistant, only when prompt data exists */}
        {!isUser && hasPromptData && !isStreaming ? (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mt-1.5 flex items-center gap-1 text-xs text-text-muted transition-colors hover:text-accent focus-visible:outline-none"
          >
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {expanded ? 'Hide full prompt' : 'Show full prompt'}
          </button>
        ) : null}

        {/* Expanded prompt viewer */}
        <AnimatePresence initial={false}>
          {expanded && hasPromptData ? (
            <motion.div
              key="prompt-expand"
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.22 }}
              className="mt-2 w-full overflow-hidden"
            >
              <PromptViewer systemPrompt={systemPrompt} rawPrompt={rawPrompt} />
            </motion.div>
          ) : null}
        </AnimatePresence>

        {!isUser && review ? <AnswerReviewCard review={review} /> : null}
        {/* Feedback controls temporarily hidden */}
      </div>
    </motion.div>
  )
})

// ─── Prompt viewer ─────────────────────────────────────────────────────────────

function PromptViewer({ systemPrompt, rawPrompt }) {
  const [activeSection, setActiveSection] = useState('full')

  const sections = [
    { id: 'full',   label: 'Full Prompt' },
    { id: 'system', label: 'System' },
  ].filter((s) => (s.id === 'system' ? systemPrompt : rawPrompt || systemPrompt))

  const content = activeSection === 'system' ? systemPrompt : rawPrompt

  return (
    <div className="rounded-xl border border-border bg-bg-tertiary overflow-hidden text-[13px]">
      {/* Section tabs */}
      <div className="flex border-b border-border">
        {sections.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setActiveSection(s.id)}
            className={`px-3 py-1.5 text-xs font-medium transition-colors ${
              activeSection === s.id
                ? 'text-accent border-b-2 border-accent -mb-px'
                : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            {s.label}
          </button>
        ))}
        <div className="flex-1" />
        <span className="self-center pr-3 text-xs text-text-muted">LLM input</span>
      </div>

      {/* Content */}
      <pre className="max-h-80 overflow-auto p-3 text-xs leading-relaxed text-text-muted whitespace-pre-wrap break-words scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent">
        {content || '—'}
      </pre>
    </div>
  )
}

// ─── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ suggestedPrompts, onSuggestedPrompt }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mx-auto flex min-h-[380px] max-w-3xl flex-col items-center justify-center py-10 text-center"
    >
      <div
        className="mb-6 inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium text-primary"
        style={{ background: 'var(--primary-soft)', borderColor: 'rgba(var(--primary-rgb) / 0.18)' }}
      >
        <span className="h-1.5 w-1.5 rounded-full bg-primary" />
        Your AI knowledge workspace
      </div>

      <div className="relative mb-5">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary-soft">
          <Sparkles className="text-primary" size={27} />
        </div>
        <div className="absolute -right-2 -top-2 h-5 w-5 rounded-full border-4 border-[var(--surface)] bg-accent animate-float" />
      </div>

      <h2 className="text-2xl font-semibold tracking-tight text-text-primary md:text-3xl">
        What can I help you explore?
      </h2>
      <p className="mb-7 mt-2 max-w-lg text-[15px] leading-relaxed text-text-muted">
        Ask a question, analyze your documents, or choose a starting point below.
      </p>

      <div className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
        {suggestedPrompts.map((prompt, index) => (
          <motion.button
            key={prompt}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 * index }}
            onClick={() => onSuggestedPrompt(prompt)}
            className="group flex min-h-14 items-center justify-between gap-3 rounded-2xl border border-border bg-bg-elevated px-4 py-3 text-left text-[15px] font-medium text-text-secondary shadow-sm transition-all duration-200 hover:border-border-hover hover:text-text-primary hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/50"
          >
            <span>{prompt}</span>
            <ArrowUpRight size={15} className="shrink-0 text-text-muted transition-transform group-group-hover:translate-x-0.5 group-hover:text-primary" />
          </motion.button>
        ))}
      </div>
    </motion.div>
  )
}

// ─── Extended progress ─────────────────────────────────────────────────────────

function ExtendedProgressIndicator({ progress }) {
  const label = progress?.node ? `${progress.node} — ${progress.phase || 'running'}` : progress?.phase || 'running'
  const percent = Number.isFinite(progress?.progress) ? progress.progress : null

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-3 flex gap-3"
    >
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-bg-tertiary">
        <Bot size={16} className="animate-pulse text-accent" />
      </div>
      <div className="max-w-[82%] flex-1">
        <div className="rounded-2xl border border-border bg-bg-elevated px-3.5 py-2.5">
          <div className="mb-1.5 flex items-center gap-2">
            <span className="text-[13px] font-semibold text-accent">{label}</span>
            {percent != null ? <span className="text-xs text-text-muted">{percent}%</span> : null}
          </div>
          <p className="mb-2 text-[13px] text-text-muted">{progress?.message || 'Processing...'}</p>
          {percent != null ? (
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-tertiary">
              <motion.div
                className="h-full rounded-full bg-primary"
                initial={{ width: 0 }}
                animate={{ width: `${percent}%` }}
                transition={{ duration: 0.4, ease: 'easeOut' }}
              />
            </div>
          ) : null}
        </div>
      </div>
    </motion.div>
  )
}

// ─── Markdown ──────────────────────────────────────────────────────────────────

const markdownComponents = {
  p:          ({ children }) => <p className="mb-2 leading-relaxed last:mb-0">{children}</p>,
  pre:        ({ children }) => <pre className="my-2 overflow-x-auto rounded-xl bg-bg-tertiary p-3 text-[13px] font-mono">{children}</pre>,
  code:       ({ inline, children }) => inline
                ? <code className="rounded bg-bg-tertiary px-1.5 py-0.5 font-mono text-[13px] text-accent">{children}</code>
                : <code>{children}</code>,
  ul:         ({ children }) => <ul className="mb-2 list-disc space-y-0.5 pl-4">{children}</ul>,
  ol:         ({ children }) => <ol className="mb-2 list-decimal space-y-0.5 pl-4">{children}</ol>,
  li:         ({ children }) => <li className="leading-relaxed">{children}</li>,
  h1:         ({ children }) => <h1 className="mb-1 text-lg font-bold">{children}</h1>,
  h2:         ({ children }) => <h2 className="mb-1 text-[15px] font-bold">{children}</h2>,
  h3:         ({ children }) => <h3 className="mb-1 text-[15px] font-semibold">{children}</h3>,
  blockquote: ({ children }) => <blockquote className="my-2 border-l-2 border-accent pl-3 italic text-text-muted">{children}</blockquote>,
  a:          ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-accent underline underline-offset-2 hover:text-accent/80">{children}</a>,
  table:      ({ children }) => <div className="my-2 overflow-x-auto"><table className="w-full border-collapse text-[13px]">{children}</table></div>,
  th:         ({ children }) => <th className="border border-border bg-bg-tertiary px-2 py-1 text-left font-semibold">{children}</th>,
  td:         ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
  hr:         () => <hr className="my-3 border-border" />,
}

function MarkdownContent({ content }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
      {content}
    </ReactMarkdown>
  )
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1.5 py-1">
      {[0, 0.2, 0.4].map((delay, index) => (
        <span key={index} className="h-2 w-2 rounded-full bg-text-muted animate-pulse" style={{ animationDelay: `${delay}s` }} />
      ))}
    </div>
  )
}
