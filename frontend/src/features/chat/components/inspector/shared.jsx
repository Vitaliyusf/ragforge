'use client'

import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'
import ProgressBar from '@/components/ui/ProgressBar'
import { techLtrProps } from '@/lib/accessibility/direction'
import { toPercent } from '@/features/chat/utils/answerQuality'
import { useI18n } from '@/i18n'

/**
 * Per-node colour and name for the graph's execution timeline.
 *
 * The keys on the left are the RAG service's own node names and never change
 * with the interface language; what a node is *called* to a reader does.
 */
const NODE_STYLE = {
  load_history:                { color: 'var(--fg-soft)', labelKey: 'node.history' },
  load_memory_light:           { color: '#8b5cf6', labelKey: 'node.memory' },
  load_memory_deep:            { color: '#8b5cf6', labelKey: 'node.memoryDeep' },
  rewrite_query:               { color: '#3b82f6', labelKey: 'node.queryRewrite' },
  query_rewrite:               { color: '#3b82f6', labelKey: 'node.queryRewrite' },
  input_guardrails:            { color: '#f59e0b', labelKey: 'node.inputGuard' },
  output_guardrails:           { color: '#f59e0b', labelKey: 'node.outputGuard' },
  retrieve_chunks_once:        { color: '#14b8a6', labelKey: 'node.retrieve' },
  retrieve_pass_one:           { color: '#14b8a6', labelKey: 'node.retrieveP1' },
  retrieve_pass_two_if_needed: { color: '#06b6d4', labelKey: 'node.retrieveP2' },
  rerank_and_merge:            { color: '#6366f1', labelKey: 'node.rerankMerge' },
  generate_answer:             { color: 'var(--success)', labelKey: 'node.generate' },
  generate_draft_answer:       { color: 'var(--success)', labelKey: 'node.draftAnswer' },
  evaluate_answer_light:       { color: 'var(--warning)', labelKey: 'node.evaluate' },
  evaluate_answer_deep:        { color: 'var(--warning)', labelKey: 'node.evaluateDeep' },
  revise_once_if_needed:       { color: 'var(--warning)', labelKey: 'node.revise' },
  persist_turn:                { color: 'var(--fg-soft)', labelKey: 'node.persist' },
  stream_done:                 { color: 'var(--fg-soft)', labelKey: 'node.done' },
}

/**
 * A node the frontend has not been taught shows its raw backend name rather
 * than a guessed translation — that name is what an operator would grep for.
 *
 * @param {string} name the graph node the trace event reported
 * @param {(key: string) => string} t
 */
export function nodeStyle(name, t) {
  const entry = NODE_STYLE[name]
  if (!entry) return { color: 'var(--fg-soft)', label: name || 'unknown' }
  return { color: entry.color, label: t(entry.labelKey) }
}

/** A labelled 0..1 score; an unmeasured score reads `n/a`, never `0%`. */
export function ScoreBar({ label, value, color = 'var(--success)' }) {
  const { t } = useI18n()
  const pct = toPercent(value)
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[13px]">
        <span className="text-text-muted">{label}</span>
        <span className="font-mono font-semibold" style={{ color: pct != null ? color : 'var(--fg-soft)' }}>
          {pct != null ? `${pct}%` : t('inspector.notAvailable')}
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
  const { t } = useI18n()
  const [revealed, setRevealed] = useState(false)
  if (content == null || content === '') return null

  const text = typeof content === 'string' ? content : JSON.stringify(content, null, 2)

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <span className="text-[13px] font-medium text-text-secondary">{label}</span>
        <button
          type="button"
          aria-label={t(revealed ? 'inspector.hideLabel' : 'inspector.revealLabel', { label })}
          onClick={() => setRevealed((value) => !value)}
          className="flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-text-muted transition-colors hover:bg-bg-tertiary hover:text-text-secondary focus-visible:outline-hidden focus-visible:ring-2"
        >
          {revealed ? <EyeOff size={12} /> : <Eye size={12} />}
          {t(revealed ? 'inspector.hide' : 'inspector.reveal')}
        </button>
      </div>
      {revealed ? (
        // A prompt, a raw model output or a JSON payload is a technical
        // artifact: it keeps its own direction and left alignment even
        // inside a Hebrew inspector, or its punctuation reorders.
        <pre
          {...techLtrProps()}
          className="max-h-56 overflow-auto whitespace-pre-wrap break-words border-t border-border bg-bg-tertiary p-3 text-left text-xs leading-relaxed text-text-muted [unicode-bidi:isolate]"
        >
          {text}
        </pre>
      ) : (
        <p className="border-t border-border bg-bg-tertiary px-3 py-2 text-xs text-text-muted">
          {t('inspector.hiddenByDefault')}
        </p>
      )}
    </div>
  )
}
