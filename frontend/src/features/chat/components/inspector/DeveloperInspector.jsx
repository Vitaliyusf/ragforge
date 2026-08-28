'use client'

import { useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronDown, X } from 'lucide-react'
import Button from '@/components/ui/Button'
import OverviewSection from './OverviewSection'
import RetrievalSection from './RetrievalSection'
import ContextSection from './ContextSection'
import GenerationSection from './GenerationSection'
import QualitySection from './QualitySection'
import TraceSection, { usableIdentifiers } from './TraceSection'

/**
 * The Developer Inspector.
 *
 * Everything the answer surface deliberately withholds — prompts, scores,
 * identifiers, per-node timings — is available here, and only here. A section
 * is rendered only when this turn actually carries data for it, so an empty
 * accordion never implies a measurement that was never taken.
 */
export default function DeveloperInspector({ message, turn, onClose, onFlowFeedback }) {
  const metadata = message?.metadata || {}
  const read = (key) => metadata[key] ?? turn?.[key] ?? null

  const debugPayloads = read('debugPayloads') || {}
  const traceEvents = read('traceEvents') || []
  const sources = read('sources') || []
  const review = read('answerReview')
  const retrievalSummary = read('retrievalSummary')
  const historySent = read('historySent')
  const feedback = read('feedback')
  const turnId = message?.turnId || metadata.turnId || turn?.turnId || null

  const identifiers = useMemo(() => ([
    ['Conversation ID', read('conversationId')],
    ['Turn ID', turnId],
    ['Request ID', read('requestId')],
    ['Trace ID', read('traceId')],
  ]), [metadata, turn, turnId]) // eslint-disable-line react-hooks/exhaustive-deps

  const sections = useMemo(() => {
    const hasContext = Boolean(
      debugPayloads.generation_context ||
      debugPayloads.generation_instructions ||
      debugPayloads.rewrite_response ||
      historySent
    )
    const hasGeneration = Boolean(
      debugPayloads.system_prompt ||
      debugPayloads.raw_prompt ||
      debugPayloads.raw_output ||
      debugPayloads.visible_reasoning_summary ||
      debugPayloads.visible_reasoning_steps ||
      traceEvents.some((event) => typeof event.node === 'string' && event.node.startsWith('generate'))
    )
    const hasQuality = Boolean(
      review ||
      debugPayloads.input_safety_flags ||
      debugPayloads.raw_input_safety_flags ||
      debugPayloads.output_safety_flags ||
      debugPayloads.raw_output_safety_flags
    )
    const hasTrace = Boolean(
      traceEvents.length ||
      usableIdentifiers(identifiers).length ||
      debugPayloads.output_safety_structured_output_candidates
    )

    return [
      {
        id: 'overview',
        label: 'Overview',
        available: true,
        render: () => (
          <OverviewSection
            mode={read('mode')}
            timestamp={message?.timestamp}
            answerLength={typeof message?.text === 'string' ? message.text.length : null}
            sources={sources}
            retrievalSummary={retrievalSummary}
            review={review}
            turnId={turnId}
            feedback={feedback}
            onFlowFeedback={onFlowFeedback}
          />
        ),
      },
      {
        id: 'retrieval',
        label: 'Retrieval',
        available: sources.length > 0,
        render: () => <RetrievalSection sources={sources} retrievalSummary={retrievalSummary} />,
      },
      {
        id: 'context',
        label: 'Context',
        available: hasContext,
        render: () => <ContextSection debugPayloads={debugPayloads} historySent={historySent} />,
      },
      {
        id: 'generation',
        label: 'Generation',
        available: hasGeneration,
        render: () => (
          <GenerationSection
            debugPayloads={debugPayloads}
            traceEvents={traceEvents}
            revisionApplied={review ? Boolean(review.revision_applied) : null}
          />
        ),
      },
      {
        id: 'quality',
        label: 'Quality',
        available: hasQuality,
        render: () => (
          <QualitySection
            review={review}
            sources={sources}
            retrievalSummary={retrievalSummary}
            debugPayloads={debugPayloads}
          />
        ),
      },
      {
        id: 'trace',
        label: 'Trace',
        available: hasTrace,
        render: () => (
          <TraceSection
            identifiers={identifiers}
            traceEvents={traceEvents}
            debugPayloads={debugPayloads}
          />
        ),
      },
    ].filter((section) => section.available)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debugPayloads, traceEvents, sources, review, retrievalSummary, historySent, feedback, identifiers, message, turnId, onFlowFeedback])

  const [openId, setOpenId] = useState('overview')

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-border bg-bg-elevated shadow-sm">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wider text-text-muted">Developer</div>
          <div className="text-[15px] font-semibold text-text-primary">Inspector</div>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} aria-label="Close inspector">
          <X size={15} />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent">
        <div className="space-y-2">
          {sections.map((section) => {
            const isOpen = openId === section.id
            return (
              <div key={section.id} className="overflow-hidden rounded-xl border border-border">
                <button
                  type="button"
                  aria-expanded={isOpen}
                  onClick={() => setOpenId(isOpen ? null : section.id)}
                  className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-start transition-colors hover:bg-bg-tertiary"
                >
                  <span className="text-[13px] font-semibold text-text-primary">{section.label}</span>
                  <ChevronDown
                    size={13}
                    className={`shrink-0 text-text-muted transition-transform ${isOpen ? 'rotate-180' : ''}`}
                  />
                </button>
                <AnimatePresence initial={false}>
                  {isOpen ? (
                    <motion.div
                      key="body"
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.18 }}
                      className="overflow-hidden"
                    >
                      <div className="border-t border-border p-3">{section.render()}</div>
                    </motion.div>
                  ) : null}
                </AnimatePresence>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
