'use client'

import { CheckCircle2, CircleDashed, Loader2, PauseCircle, XCircle } from 'lucide-react'
import StatusIndicator from '@/components/status/StatusIndicator'
import { usePrefersReducedMotion } from '@/lib/accessibility/usePrefersReducedMotion'
import { useI18n } from '@/i18n'
import { getDocumentStatus, getStatusPresentation, summarizePipeline } from '../documentModel'

/**
 * The Status cell: one badge, one word.
 *
 * The pipeline detail is a separate cell, so this never repeats it.
 */
export function DocumentStatusBadge({ file, size = 'sm' }) {
  const { t } = useI18n()
  const status = getDocumentStatus(file)
  const { labelKey, tone } = getStatusPresentation(status)
  return <StatusIndicator tone={tone} label={t(labelKey)} size={size} />
}

const PIPELINE_ICONS = {
  done: CheckCircle2,
  running: Loader2,
  failed: XCircle,
  blocked: PauseCircle,
  idle: CircleDashed,
  queued: CircleDashed,
}

const PIPELINE_COLORS = {
  done: 'var(--fg-soft)',
  running: 'var(--status-live)',
  failed: 'var(--danger)',
  blocked: 'var(--warning)',
  idle: 'var(--fg-soft)',
  queued: 'var(--fg-muted)',
}

/**
 * The Pipeline cell: the stage that explains the status, and nothing else.
 *
 * A ready document reads "Indexed" — not eight ticks and a fraction — and
 * only a genuinely running stage is allowed to animate.
 */
export function DocumentPipelineCell({ file }) {
  const { t } = useI18n()
  const reducedMotion = usePrefersReducedMotion()
  const pipeline = summarizePipeline(file)
  const Icon = PIPELINE_ICONS[pipeline.state] ?? CircleDashed
  const spinning = pipeline.state === 'running' && !reducedMotion

  return (
    <span
      className="inline-flex items-center gap-1.5 text-[13px] whitespace-nowrap"
      style={{ color: PIPELINE_COLORS[pipeline.state] ?? 'var(--fg-soft)' }}
      data-pipeline-state={pipeline.state}
    >
      <Icon size={12} className={`shrink-0 ${spinning ? 'animate-spin' : ''}`} aria-hidden="true" />
      {t(pipeline.labelKey)}{pipeline.suffix ?? ''}
    </span>
  )
}
