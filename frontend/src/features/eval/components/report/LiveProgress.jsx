'use client'

import ProgressBar from '@/components/ui/ProgressBar'
import { EMPTY } from '@/features/metrics/components/metricsConfig'
import { PHASE_LABEL_KEYS, STALL_SECONDS, ageSeconds, formatAge, formatElapsed } from '../../evalProfiles'
import { Fact } from './primitives'
import { useI18n } from '@/i18n'

/**
 * Item-level progress for the phase that is executing.
 *
 * Every number here is the server's own persisted progress; nothing is
 * interpolated on the client, because a bar that keeps moving after the
 * backend has stopped is worse than no bar. The denominator is the
 * benchmark's items-per-phase — with none, the bar renders empty rather
 * than guessing at one.
 */
export default function LiveProgress({ phase, itemsPerPhase }) {
  const { t } = useI18n()
  if (!phase) return null
  const progress = phase.item_progress || {}
  const total = Number(itemsPerPhase ?? 0)
  const completed = Number(progress.items_completed ?? 0)
  const percent = total ? Math.round((completed / total) * 100) : null
  const elapsed = formatElapsed(progress.phase_started_at)
  const staleSeconds = ageSeconds(progress.last_progress_at)
  const label = PHASE_LABEL_KEYS[phase.name] ? t(PHASE_LABEL_KEYS[phase.name]) : phase.name

  return (
    <div
      className="rounded-xl border p-3"
      style={{ borderColor: 'var(--border)', background: 'var(--surface-hover)' }}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-[13px]">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums" style={{ color: 'var(--fg-muted)' }}>
          {t('evalReport.itemsOfTotal', { completed, total: total || EMPTY })}
          {percent !== null ? ` · ${percent}%` : ''}
        </span>
      </div>

      <ProgressBar
        className="mt-2"
        value={percent}
        color="var(--primary)"
        aria-label={t('evalReport.itemProgress', { name: label })}
      />

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[13px] sm:grid-cols-4">
        <Fact label={t('evalReport.successful')} value={progress.items_succeeded ?? 0} />
        <Fact label={t('evalReport.guardrailBlocked')} value={progress.items_guardrail_blocked ?? 0} />
        <Fact label={t('evalReport.failedItems')} value={progress.items_failed ?? 0} />
        <Fact label={t('evalReport.inFlight')} value={progress.items_in_flight ?? 0} />
      </dl>

      <p className="mt-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
        {t('evalReport.elapsed', { duration: elapsed || EMPTY })}
        {staleSeconds !== null
          ? ` · ${t('evalReport.lastProgress', { age: formatAge(staleSeconds) })}`
          : ''}
      </p>

      {staleSeconds !== null && staleSeconds >= STALL_SECONDS && (
        <p className="mt-1 text-[12px]" style={{ color: 'var(--warning)' }}>
          {t('evalReport.possibleStall', { age: formatAge(staleSeconds) })}
        </p>
      )}
    </div>
  )
}
