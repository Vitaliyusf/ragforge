'use client'

import { DataCell } from '@/components/ui/DataDisplay'
import { formatDuration } from '@/lib/formatting/datetime'
import { RedactedBlock, Empty } from './shared'

/**
 * The generation step itself: what the model was asked, what it produced, and
 * how long it took.
 *
 * Token counts, TTFT and the generation model name are not carried on the
 * `done` event, so they are absent here rather than guessed — an unmeasured
 * number must never be rendered as a real one.
 */
export default function GenerationSection({ debugPayloads = {}, traceEvents = [], revisionApplied }) {
  const generationMs = traceEvents
    .filter((event) => typeof event.node === 'string' && event.node.startsWith('generate'))
    .reduce((total, event) => total + (Number.isFinite(event.latency) ? event.latency : 0), 0)
  const generationLatency = generationMs > 0 ? formatDuration(generationMs) : null

  const blocks = [
    { label: 'System prompt', content: debugPayloads.system_prompt },
    { label: 'User prompt', content: debugPayloads.raw_prompt },
    {
      label: 'Reasoning summary',
      content: debugPayloads.visible_reasoning_summary ?? debugPayloads.visible_reasoning_steps,
    },
    { label: 'Raw output', content: debugPayloads.raw_output },
  ].filter((block) => block.content != null && block.content !== '')

  if (!blocks.length && !generationLatency && revisionApplied == null) {
    return <Empty label="No generation data for this turn" />
  }

  return (
    <div className="space-y-3">
      {(generationLatency || revisionApplied != null) ? (
        <div className="grid grid-cols-2 gap-2">
          {generationLatency ? (
            <DataCell reverse center mono label="Generation time" value={generationLatency} />
          ) : null}
          {revisionApplied != null ? (
            <DataCell reverse center label="Revision" value={revisionApplied ? 'Applied' : 'Not applied'} />
          ) : null}
        </div>
      ) : null}

      <div className="space-y-2">
        {blocks.map((block) => (
          <RedactedBlock key={block.label} label={block.label} content={block.content} />
        ))}
      </div>
    </div>
  )
}
