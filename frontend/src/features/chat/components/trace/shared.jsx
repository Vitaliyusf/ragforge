'use client'

import ProgressBar from '@/components/ui/ProgressBar'

const NODE_STYLE = {
  load_history:              { color: 'var(--fg-soft)', label: 'History' },
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
  generate_answer:           { color: 'var(--success)', label: 'Generate' },
  generate_draft_answer:     { color: 'var(--success)', label: 'Draft Answer' },
  evaluate_answer_light:     { color: 'var(--warning)', label: 'Evaluate' },
  evaluate_answer_deep:      { color: 'var(--warning)', label: 'Evaluate (deep)' },
  revise_once_if_needed:     { color: 'var(--warning)', label: 'Revise' },
  stream_done:               { color: 'var(--fg-soft)', label: 'Done' },
}

function nodeStyle(name) {
  return NODE_STYLE[name] || { color: 'var(--fg-soft)', label: name || 'unknown' }
}

function ScoreBar({ label, value, color = 'var(--success)' }) {
  const pct = value != null ? Math.round(value * 100) : null
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

function scoreColor(value) {
  if (value == null) return 'var(--fg-soft)'
  if (value >= 0.75) return 'var(--success)'
  if (value >= 0.5)  return 'var(--warning)'
  return 'var(--danger)'
}

function Empty({ label }) {
  return (
    <div className="flex h-24 items-center justify-center rounded-lg border border-border bg-bg-tertiary">
      <span className="text-[13px] text-text-muted">{label}</span>
    </div>
  )
}

export { NODE_STYLE, nodeStyle, ScoreBar, scoreColor, Empty }
