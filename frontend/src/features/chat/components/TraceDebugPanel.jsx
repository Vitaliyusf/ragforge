'use client'

import { useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Zap, Database, FileText, ShieldCheck, ChevronDown, ChevronUp } from 'lucide-react'
import Button from '@/components/ui/Button'

// ─── Node styling ──────────────────────────────────────────────────────────────

const NODE_STYLE = {
  load_history:              { color: '#6b7280', label: 'History' },
  load_memory_light:         { color: '#8b5cf6', label: 'Memory' },
  load_memory_deep:          { color: '#8b5cf6', label: 'Memory (deep)' },
  rewrite_query:             { color: '#3b82f6', label: 'Query Rewrite' },
  query_rewrite:             { color: '#3b82f6', label: 'Query Rewrite' },
  input_guardrails:          { color: '#f59e0b', label: 'Input Guard' },
  output_guardrails:         { color: '#f59e0b', label: 'Output Guard' },
  retrieve_chunks_once:      { color: '#14b8a6', label: 'Retrieve' },
  retrieve_pass_one:         { color: '#14b8a6', label: 'Retrieve P1' },
  retrieve_pass_two_if_needed: { color: '#06b6d4', label: 'Retrieve P2' },
  rerank_and_merge:          { color: '#6366f1', label: 'Rerank & Merge' },
  generate_answer:           { color: '#22c55e', label: 'Generate' },
  generate_draft_answer:     { color: '#22c55e', label: 'Draft Answer' },
  evaluate_answer_light:     { color: '#eab308', label: 'Evaluate' },
  evaluate_answer_deep:      { color: '#eab308', label: 'Evaluate (deep)' },
  revise_once_if_needed:     { color: '#f97316', label: 'Revise' },
  stream_done:               { color: '#6b7280', label: 'Done' },
}

function nodeStyle(name) {
  return NODE_STYLE[name] || { color: '#6b7280', label: name || 'unknown' }
}

// ─── Tabs ──────────────────────────────────────────────────────────────────────

const TABS = [
  { id: 'pipeline', label: 'Pipeline', icon: Zap },
  { id: 'sources',  label: 'Sources',  icon: Database },
  { id: 'quality',  label: 'Quality',  icon: ShieldCheck },
  { id: 'prompt',   label: 'Prompt',   icon: FileText },
]

// ─── Score bar ─────────────────────────────────────────────────────────────────

function ScoreBar({ label, value, color = '#22c55e' }) {
  const pct = value != null ? Math.round(value * 100) : null
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="text-text-muted">{label}</span>
        <span className="font-mono font-semibold" style={{ color: pct != null ? color : '#6b7280' }}>
          {pct != null ? `${pct}%` : 'n/a'}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-bg-tertiary">
        {pct != null ? (
          <motion.div
            className="h-full rounded-full"
            style={{ backgroundColor: color }}
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
          />
        ) : null}
      </div>
    </div>
  )
}

function scoreColor(value) {
  if (value == null) return '#6b7280'
  if (value >= 0.75) return '#22c55e'
  if (value >= 0.5)  return '#eab308'
  return '#ef4444'
}

// ─── Pipeline tab ──────────────────────────────────────────────────────────────

function PipelineTab({ traceEvents, retrievalSummary }) {
  if (!traceEvents.length) {
    return <Empty label="No pipeline data for this turn" />
  }

  const totalLatency = traceEvents.reduce((sum, t) => sum + (t.latency || 0), 0)
  const maxLatency   = Math.max(...traceEvents.map((t) => t.latency || 0), 1)

  return (
    <div className="space-y-3">
      {retrievalSummary ? (
        <div className="grid grid-cols-2 gap-2">
          <Stat label="Chunks used" value={retrievalSummary.chunk_count ?? '—'} />
          <Stat label="Total latency" value={`${Math.round(totalLatency)} ms`} />
        </div>
      ) : (
        <Stat label="Total latency" value={`${Math.round(totalLatency)} ms`} />
      )}

      <div className="space-y-1.5">
        {traceEvents.map((trace, index) => {
          const { color, label } = nodeStyle(trace.node)
          const pct = Math.max(4, Math.round(((trace.latency || 0) / maxLatency) * 100))
          const counters = trace.counters && Object.keys(trace.counters).length > 0
            ? Object.entries(trace.counters)
            : null

          return (
            <div key={`${trace.node}-${index}`} className="rounded-lg border border-border bg-bg-tertiary p-2.5">
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <span className="truncate text-xs font-medium text-text-primary">{label}</span>
                  {trace.decision && trace.decision !== 'completed' && trace.decision !== trace.node ? (
                    <span className="shrink-0 rounded-full bg-bg-elevated px-1.5 py-0.5 text-[10px] text-text-muted">
                      Decision: {trace.decision}
                    </span>
                  ) : null}
                </div>
                <span className="shrink-0 font-mono text-[11px] text-text-muted">
                  {trace.latency != null ? `${trace.latency} ms` : '—'}
                </span>
              </div>

              <div className="mb-1 h-1 w-full overflow-hidden rounded-full bg-bg-elevated">
                <motion.div
                  className="h-full rounded-full"
                  style={{ backgroundColor: color, opacity: 0.7 }}
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ duration: 0.4, delay: index * 0.04, ease: 'easeOut' }}
                />
              </div>

              {counters ? (
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 pt-0.5">
                  {counters.map(([k, v]) => (
                    <span key={k} className="text-[10px] text-text-muted">
                      <span className="text-text-secondary">{v}</span> {k.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Sources tab ───────────────────────────────────────────────────────────────

function SourcesTab({ sources, retrievalSummary }) {
  const [expandedIndex, setExpandedIndex] = useState(null)

  if (!sources.length) {
    return <Empty label="No sources retrieved for this turn" />
  }

  const topScore   = sources[0]?.score ?? 0
  const bottomScore = sources[sources.length - 1]?.score ?? 0

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Chunks" value={sources.length} />
        <Stat label="Top score" value={topScore ? `${(topScore * 100).toFixed(0)}%` : '—'} />
        <Stat label="Min score" value={bottomScore ? `${(bottomScore * 100).toFixed(0)}%` : '—'} />
      </div>

      <div className="space-y-2">
        {sources.map((src, index) => {
          const score  = src.score ?? src.similarity ?? null
          const pct    = score != null ? score * 100 : null
          const color  = score != null ? scoreColor(score) : '#6b7280'
          const name   = src.source_name || src.source || src.filename || `chunk-${index + 1}`
          const isOpen = expandedIndex === index

          return (
            <div key={src.chunk_id || index} className="rounded-lg border border-border bg-bg-tertiary overflow-hidden">
              <button
                type="button"
                onClick={() => setExpandedIndex(isOpen ? null : index)}
                className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left hover:bg-bg-elevated transition-colors"
              >
                <div
                  className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded text-[10px] font-bold text-white"
                  style={{ backgroundColor: color }}
                >
                  {index + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-xs font-medium text-text-primary">{name}</div>
                  <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-bg-elevated">
                    {pct != null ? (
                      <motion.div
                        className="h-full rounded-full"
                        style={{ backgroundColor: color }}
                        initial={{ width: 0 }}
                        animate={{ width: `${pct}%` }}
                        transition={{ duration: 0.4, delay: index * 0.05, ease: 'easeOut' }}
                      />
                    ) : null}
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-[10px] text-text-muted">
                    {pct != null ? (
                      <span style={{ color }} className="font-mono font-semibold">{pct.toFixed(1)}%</span>
                    ) : null}
                    {src.chunk_index != null ? <span>chunk #{src.chunk_index}</span> : null}
                    {src.page != null ? <span>p.{src.page}</span> : null}
                  </div>
                </div>
                {isOpen ? <ChevronUp size={12} className="mt-1 shrink-0 text-text-muted" /> : <ChevronDown size={12} className="mt-1 shrink-0 text-text-muted" />}
              </button>

              <AnimatePresence initial={false}>
                {isOpen ? (
                  <motion.div
                    key="preview"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="overflow-hidden"
                  >
                    <div className="border-t border-border px-3 pb-3 pt-2">
                      <p className="text-[11px] leading-relaxed text-text-muted line-clamp-6">
                        {src.text_preview || src.text || 'No preview available'}
                      </p>
                    </div>
                  </motion.div>
                ) : null}
              </AnimatePresence>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Quality tab ───────────────────────────────────────────────────────────────

function QualityTab({ answerReview }) {
  if (!answerReview) {
    return <Empty label="No answer evaluation for this turn" />
  }

  const verdict = answerReview.verdict || 'unknown'
  const verdictColor = verdict === 'pass' ? '#22c55e' : verdict === 'revise' ? '#f97316' : verdict === 'unavailable' ? '#6b7280' : '#ef4444'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between rounded-lg border border-border bg-bg-tertiary px-3 py-2.5">
        <span className="text-xs text-text-muted">Verdict</span>
        <span
          className="rounded-full px-2.5 py-0.5 text-xs font-semibold capitalize"
          style={{ backgroundColor: `${verdictColor}20`, color: verdictColor }}
        >
          {verdict}
        </span>
      </div>

      <div className="space-y-3">
        <ScoreBar
          label="Groundedness"
          value={answerReview.groundedness_score}
          color={scoreColor(answerReview.groundedness_score)}
        />
        <ScoreBar
          label="Completeness"
          value={answerReview.completeness_score}
          color={scoreColor(answerReview.completeness_score)}
        />
        <ScoreBar
          label="Safety"
          value={answerReview.safety_score}
          color={scoreColor(answerReview.safety_score)}
        />
      </div>

      {answerReview.issues?.length > 0 ? (
        <div>
          <div className="mb-1.5 text-xs font-medium text-text-muted">Issues</div>
          <div className="space-y-1">
            {answerReview.issues.map((issue, i) => (
              <div key={i} className="flex items-start gap-2 rounded-lg bg-bg-tertiary px-2.5 py-1.5 text-xs text-text-secondary">
                <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-orange-400" />
                {issue}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="rounded-lg bg-bg-tertiary px-3 py-2 text-xs text-text-muted">No issues flagged</div>
      )}

      {answerReview.revision_applied ? (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-xs text-text-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          Answer was revised
        </div>
      ) : null}
    </div>
  )
}

// ─── Prompt tab ────────────────────────────────────────────────────────────────

function PromptTab({ debugPayloads, metadata }) {
  const [openBlock, setOpenBlock] = useState(null)

  const safetyFlags = (debugPayloads.raw_input_safety_flags || debugPayloads.raw_output_safety_flags)
    ? {
        input: debugPayloads.raw_input_safety_flags || null,
        output: debugPayloads.raw_output_safety_flags || null,
      }
    : null
  const structuredCandidates = debugPayloads.output_safety_structured_output_candidates
    ? {
        selected_payload_index: debugPayloads.output_safety_structured_output_selected_index,
        selection_policy: debugPayloads.output_safety_structured_output_selection_policy,
        extraction_mode: debugPayloads.output_safety_structured_output_extraction_mode,
        candidates: debugPayloads.output_safety_structured_output_candidates,
        raw_output: debugPayloads.output_safety_raw_output,
      }
    : null

  const blocks = [
    { id: 'system', label: 'System prompt', content: debugPayloads.system_prompt },
    { id: 'user',   label: 'User prompt',   content: debugPayloads.raw_prompt },
    { id: 'reasoning', label: 'Reasoning / Rewrite Summary', content: debugPayloads.visible_reasoning_steps },
    { id: 'safety', label: 'Safety Flags', content: safetyFlags },
    { id: 'output', label: 'Raw output',    content: debugPayloads.raw_output },
    { id: 'rewrite', label: 'Query rewrite', content: debugPayloads.rewrite_response },
    { id: 'structured', label: 'Structured Output Candidates', content: structuredCandidates },
  ].filter((b) => b.content)

  if (!blocks.length) {
    return <Empty label="No prompt data available" />
  }

  return (
    <div className="space-y-2">
      {blocks.map((block) => {
        const isOpen = openBlock === block.id
        return (
          <div key={block.id} className="rounded-lg border border-border overflow-hidden">
            <button
              type="button"
              onClick={() => setOpenBlock(isOpen ? null : block.id)}
              className="flex w-full items-center justify-between px-3 py-2.5 text-left hover:bg-bg-tertiary transition-colors"
            >
              <span className="text-xs font-medium text-text-secondary">{block.label}</span>
              {isOpen ? <ChevronUp size={12} className="text-text-muted" /> : <ChevronDown size={12} className="text-text-muted" />}
            </button>
            <AnimatePresence initial={false}>
              {isOpen ? (
                <motion.div
                  key="body"
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <pre className="max-h-56 overflow-auto border-t border-border bg-bg-tertiary p-3 text-[11px] leading-relaxed text-text-muted whitespace-pre-wrap break-words">
                    {typeof block.content === 'string' ? block.content : JSON.stringify(block.content, null, 2)}
                  </pre>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>
        )
      })}
    </div>
  )
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

function Stat({ label, value }) {
  return (
    <div className="rounded-lg border border-border bg-bg-tertiary px-2.5 py-2 text-center">
      <div className="font-mono text-sm font-bold text-text-primary">{value}</div>
      <div className="mt-0.5 text-[10px] text-text-muted">{label}</div>
    </div>
  )
}

function Empty({ label }) {
  return (
    <div className="flex h-24 items-center justify-center rounded-lg border border-border bg-bg-tertiary">
      <span className="text-xs text-text-muted">{label}</span>
    </div>
  )
}

// ─── Main panel ────────────────────────────────────────────────────────────────

export default function TraceDebugPanel({ message, turn, onClose }) {
  const [activeTab, setActiveTab] = useState('pipeline')

  const metadata        = message?.metadata || {}
  const traceEvents     = useMemo(() => metadata.traceEvents || turn?.traceEvents || [], [metadata.traceEvents, turn?.traceEvents])
  const sources         = useMemo(() => metadata.sources || turn?.sources || [], [metadata.sources, turn?.sources])
  const answerReview    = metadata.answerReview || turn?.answerReview || null
  const retrievalSummary = metadata.retrievalSummary || turn?.retrievalSummary || null
  const debugPayloads   = metadata.debugPayloads || turn?.debugPayloads || {}

  const tabBadge = {
    pipeline: traceEvents.length || null,
    sources:  sources.length || null,
    quality:  answerReview ? (answerReview.verdict === 'pass' ? '✓' : answerReview.verdict === 'unavailable' ? '–' : '!') : null,
    prompt:   null,
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-bg-elevated shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">Trace / Debug</div>
          <div className="text-sm font-semibold text-text-primary">Turn Metrics</div>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close panel">
          <X size={15} />
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-border">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveTab(id)}
            className={`relative flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[10px] font-medium transition-colors ${
              activeTab === id ? 'text-accent' : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            <Icon size={13} />
            <span>{label}</span>
            {tabBadge[id] != null ? (
              <span className={`absolute right-1 top-1.5 rounded-full px-1 text-[9px] font-bold ${
                activeTab === id ? 'bg-accent text-white' : 'bg-bg-tertiary text-text-muted'
              }`}>
                {tabBadge[id]}
              </span>
            ) : null}
            {activeTab === id ? (
              <motion.div
                layoutId="tab-indicator"
                className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent rounded-full"
              />
            ) : null}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto px-3 py-3 scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
          >
            {activeTab === 'pipeline' && (
              <PipelineTab traceEvents={traceEvents} retrievalSummary={retrievalSummary} />
            )}
            {activeTab === 'sources' && (
              <SourcesTab sources={sources} retrievalSummary={retrievalSummary} />
            )}
            {activeTab === 'quality' && (
              <QualityTab answerReview={answerReview} />
            )}
            {activeTab === 'prompt' && (
              <PromptTab debugPayloads={debugPayloads} metadata={metadata} />
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  )
}
