'use client'

import { useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X, Zap, Database, FileText, ShieldCheck, ChevronDown, ChevronUp } from 'lucide-react'
import Button from '@/components/ui/Button'
import PipelineTab from './trace/PipelineTab'
import SourcesTab from './trace/SourcesTab'
import QualityTab from './trace/QualityTab'
import PromptTab from './trace/PromptTab'


const TABS = [
  { id: 'pipeline', label: 'Pipeline', icon: Zap },
  { id: 'sources',  label: 'Sources',  icon: Database },
  { id: 'quality',  label: 'Quality',  icon: ShieldCheck },
  { id: 'prompt',   label: 'Prompt',   icon: FileText },
]


// ─── Main panel ────────────────────────────────────────────────────────────────

export default function TraceDebugPanel({ message, turn, onClose }) {
  const [activeTab, setActiveTab] = useState('pipeline')

  const metadata        = message?.metadata || {}
  const traceEvents     = useMemo(() => metadata.traceEvents || turn?.traceEvents || [], [metadata.traceEvents, turn?.traceEvents])
  const sources         = useMemo(() => metadata.sources || turn?.sources || [], [metadata.sources, turn?.sources])
  const answerReview    = metadata.answerReview || turn?.answerReview || null
  const retrievalSummary = metadata.retrievalSummary || turn?.retrievalSummary || null
  const debugPayloads   = metadata.debugPayloads || turn?.debugPayloads || {}

  // Correlation ids for matching this turn against gateway/service logs. Kept
  // outside the tab strip so they stay readable whichever tab is open.
  const identifiers = useMemo(() => ([
    ['Conversation ID', metadata.conversationId || turn?.conversationId],
    ['Turn ID',         metadata.turnId         || turn?.turnId],
    ['Request ID',      metadata.requestId      || turn?.requestId],
    ['Trace ID',        metadata.traceId        || turn?.traceId],
  ].filter(([, value]) => Boolean(value))
    .map(([label, value]) => ({ label, value: String(value) }))
  ), [metadata.conversationId, metadata.turnId, metadata.requestId, metadata.traceId,
      turn?.conversationId, turn?.turnId, turn?.requestId, turn?.traceId])

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
          <div className="text-xs font-semibold uppercase tracking-wider text-text-muted">Trace / Debug</div>
          <div className="text-[15px] font-semibold text-text-primary">Turn Metrics</div>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close panel">
          <X size={15} />
        </Button>
      </div>

      {/* Correlation identifiers */}
      {identifiers.length > 0 ? (
        <div className="grid grid-cols-2 gap-x-3 gap-y-2 border-b border-border px-4 py-2.5">
          {identifiers.map(({ label, value }) => (
            <div key={label} className="min-w-0">
              <div className="text-xs uppercase tracking-wide text-text-muted">{label}</div>
              <div className="truncate font-mono text-xs text-text-secondary" title={value}>
                {value}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {/* Tabs */}
      <div className="flex border-b border-border">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveTab(id)}
            className={`relative flex flex-1 flex-col items-center gap-0.5 py-2.5 text-xs font-medium transition-colors ${
              activeTab === id ? 'text-accent' : 'text-text-muted hover:text-text-secondary'
            }`}
          >
            <Icon size={13} />
            <span>{label}</span>
            {tabBadge[id] != null ? (
              <span className={`absolute right-1 top-1.5 rounded-full px-1 text-xs font-bold ${
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
