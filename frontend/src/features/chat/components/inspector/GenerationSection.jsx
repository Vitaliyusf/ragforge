'use client'

import { DataCell } from '@/components/ui/DataDisplay'
import { formatDuration } from '@/lib/formatting/datetime'
import { RedactedBlock, Empty } from './shared'
import { useI18n } from '@/i18n'

/**
 * The generation step itself: what the model was asked, what it produced, and
 * how long it took.
 *
 * Token counts, TTFT and the generation model name are not carried on the
 * `done` event, so they are absent here rather than guessed — an unmeasured
 * number must never be rendered as a real one.
 */
export default function GenerationSection({ debugPayloads = {}, traceEvents = [], revisionApplied }) {
  const { t } = useI18n()
  const generationMs = traceEvents
    .filter((event) => typeof event.node === 'string' && event.node.startsWith('generate'))
    .reduce((total, event) => total + (Number.isFinite(event.latency) ? event.latency : 0), 0)
  const generationLatency = generationMs > 0 ? formatDuration(generationMs) : null

  const blocks = [
    { label: t('inspector.systemPrompt'), content: debugPayloads.system_prompt },
    { label: t('inspector.userPrompt'), content: debugPayloads.raw_prompt },
    {
      label: t('inspector.reasoningSummary'),
      content: debugPayloads.visible_reasoning_summary ?? debugPayloads.visible_reasoning_steps,
    },
    { label: t('inspector.rawOutput'), content: debugPayloads.raw_output },
  ].filter((block) => block.content != null && block.content !== '')

  if (!blocks.length && !generationLatency && revisionApplied == null) {
    return <Empty label={t('inspector.emptyGeneration')} />
  }

  return (
    <div className="space-y-3">
      {(generationLatency || revisionApplied != null) ? (
        <div className="grid grid-cols-2 gap-2">
          {generationLatency ? (
            <DataCell reverse center mono label={t('inspector.generationTime')} value={generationLatency} />
          ) : null}
          {revisionApplied != null ? (
            <DataCell
              reverse
              center
              label={t('inspector.revision')}
              value={t(revisionApplied ? 'inspector.revisionApplied' : 'inspector.revisionNotApplied')}
            />
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
