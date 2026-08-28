'use client'

import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import ProgressBar from '@/components/ui/ProgressBar'
import { toPercent } from '@/features/chat/utils/answerQuality'

/** Per-node colour and human label for the graph's execution timeline. */
const NODE_STYLE = {
  load_history:                { color: 'var(--fg-soft)', label: 'History' },
  load_memory_light:           { color: '#8b5cf6', label: 'Memory' },
  load_memory_deep:            { color: '#8b5cf6', label: 'Memory (deep)' },
  rewrite_query:               { color: '#3b82f6', label: 'Query Rewrite' },
  query_rewrite:               { color: '#3b82f6', label: 'Query Rewrite' },
  input_guardrails:            { color: '#f59e0b', label: 'Input Guard' },
  output_guardrails:           { color: '#f59e0b', label: 'Output Guard' },
  retrieve_chunks_once:        { color: '#14b8a6', label: 'Retrieve' },
  retrieve_pass_one:           { color: '#14b8a6', label: 'Retrieve P1' },
  retrieve_pass_two_if_needed: { color: '#06b6d4', label: 'Retrieve P2' },
  rerank_and_merge:            { color: '#6366f1', label: 'Rerank & Merge' },
  generate_answer:             { color: 'var(--success)', label: 'Generate' },
  generate_draft_answer:       { color: 'var(--success)', label: 'Draft Answer' },
  evaluate_answer_light:       { color: 'var(--warning)', label: 'Evaluate' },
  evaluate_answer_deep:        { color: 'var(--warning)', label: 'Evaluate (deep)' },
  revise_once_if_needed:       { color: 'var(--warning)', label: 'Revise' },
  persist_turn:                { color: 'var(--fg-soft)', label: 'Persist' },
  stream_done:                 { color: 'var(--fg-soft)', label: 'Done' },
}

export function nodeStyle(name) {
  return NODE_STYLE[name] || { color: 'var(--fg-soft)', label: name || 'unknown' }
}

/** A labelled 0..1 score; an unmeasured score reads `n/a`, never `0%`. */
export function ScoreBar({ label, value, color = 'var(--success)' }) {
  const pct = toPercent(value)
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[13px]">
        <span className="text-text-muted">{label}</span>
        <span className="font-mono font-semibold" style={{ color: pct != null ? color : 'var(--fg-soft)' }}>
          {pct != null ? `${pct}%` : 'n/a'}
        </span>
      </div>
      <ProgressBar value={pct} color={color} aria-label={label} />
    </div>
  )
}

/** Placeholder for a section that has no data for this turn. */
export function Empty({ label }) {
  return (
    <div className="flex h-20 items-center justify-center rounded-lg border border-border bg-bg-tertiary">
      <span className="text-[13px] text-text-muted">{label}</span>
    </div>
  )
}

/** A short technical value that must not be reordered by surrounding RTL text. */
export function TechnicalValue({ children, title }) {
  return (
    <span dir="ltr" className="truncate font-mono text-xs text-text-secondary [unicode-bidi:isolate]" title={title}>
      {children}
    </span>
  )
}

/**
 * Model input/output that can echo private document text.
 *
 * It stays masked until the reader explicitly asks for it, so opening the
 * inspector never puts retrieved content on screen by itself.
 */
export function RedactedBlock({ label, content }) {
  const [revealed, setRevealed] = useState(false)
  if (content == null || content === '') return null

  const text = typeof content === 'string' ? content : JSON.stringify(content, null, 2)

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <span className="text-[13px] font-medium text-text-secondary">{label}</span>
        <button
          type="button"
          aria-label={`${revealed ? 'Hide' : 'Reveal'} ${label}`}
          onClick={() => setRevealed((value) => !value)}
          className="flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-text-muted transition-colors hover:bg-bg-tertiary hover:text-text-secondary focus-visible:outline-hidden focus-visible:ring-2"
        >
          {revealed ? <EyeOff size={12} /> : <Eye size={12} />}
          {revealed ? 'Hide' : 'Reveal'}
        </button>
      </div>
      {revealed ? (
        <pre
          dir="ltr"
          className="max-h-56 overflow-auto whitespace-pre-wrap break-words border-t border-border bg-bg-tertiary p-3 text-xs leading-relaxed text-text-muted"
        >
          {text}
        </pre>
      ) : (
        <p className="border-t border-border bg-bg-tertiary px-3 py-2 text-xs text-text-muted">
          Hidden by default — may contain document content.
        </p>
      )}
    </div>
  )
}
