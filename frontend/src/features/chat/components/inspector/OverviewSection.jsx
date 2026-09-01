'use client'

import { GitBranch, MessageSquareWarning } from 'lucide-react'
import Button from '@/components/ui/Button'
import { DataCell } from '@/components/ui/DataDisplay'
import { formatAbsoluteDateTime } from '@/lib/formatting/datetime'
import { buildAnswerQuality } from '@/features/chat/utils/answerQuality'
import { useI18n } from '@/i18n'

/**
 * What this turn was and how it ended, in one screen.
 *
 * Flow feedback lives here rather than under the answer: judging whether the
 * pipeline behaved sensibly is an engineering question, and the reader of a
 * plain answer should not be asked it.
 */
export default function OverviewSection({
  mode,
  timestamp,
  answerLength,
  sources,
  retrievalSummary,
  review,
  turnId,
  feedback,
  onFlowFeedback,
}) {
  const { locale, t } = useI18n()
  const quality = buildAnswerQuality({ review, sources, retrievalSummary })
  const answeredAt = formatAbsoluteDateTime(timestamp, locale)
  const flowState = feedback?.flow

  const cells = [
    mode
      ? {
          label: t('inspector.mode'),
          value: t(mode === 'extended' ? 'chat.deepResearch' : 'chat.quickAnswer'),
        }
      : null,
    answeredAt ? { label: t('inspector.answered'), value: answeredAt } : null,
    { label: t('inspector.sources'), value: quality.sourceCount },
    { label: t('inspector.chunks'), value: quality.chunkCount },
    Number.isFinite(answerLength)
      ? { label: t('inspector.answerLength'), value: t('inspector.chars', { count: answerLength }) }
      : null,
  ].filter(Boolean)

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-border bg-bg-tertiary px-3 py-2.5 text-[13px] text-text-secondary">
        {quality.kind === 'unsupported'
          ? t('chat.answerabilityLine', { value: t(quality.answerabilityKey) })
          : (quality.partKeys.map((part) => t(part.key, part.vars)).join(' · ')
             || t('inspector.noQualitySignal'))}
      </div>

      <div className="grid grid-cols-2 gap-2">
        {cells.map((cell) => (
          <DataCell key={cell.label} reverse center label={cell.label} value={cell.value} />
        ))}
      </div>

      {turnId && onFlowFeedback ? (
        <div>
          <div className="mb-1.5 text-[13px] font-medium text-text-muted">{t('inspector.flowQuestion')}</div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={flowState?.status === 'sending'}
              onClick={() => onFlowFeedback(turnId, { category: 'flow_clear', label: 'clear' })}
              leftIcon={<GitBranch size={14} />}
            >
              {t('inspector.flowClear')}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              disabled={flowState?.status === 'sending'}
              onClick={() => onFlowFeedback(turnId, { category: 'flow_confusing', label: 'confusing' })}
              leftIcon={<MessageSquareWarning size={14} />}
            >
              {t('inspector.flowConfusing')}
            </Button>
            {flowState?.status === 'sent' ? (
              <span className="text-xs text-text-muted">{t('inspector.sent')}</span>
            ) : null}
            {flowState?.status === 'error' ? (
              <span className="text-xs text-[var(--danger)]">{flowState.error || t('common.failed')}</span>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}
