'use client'

import ProgressBar from '@/components/ui/ProgressBar'
import { EMPTY } from '@/features/metrics/components/metricsConfig'
import { PHASE_LABELS, STALL_SECONDS, ageSeconds, formatAge, formatElapsed } from '../../evalProfiles'
import { Fact } from './primitives'

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
  if (!phase) return null
  const progress = phase.item_progress || {}
  const total = Number(itemsPerPhase ?? 0)
  const completed = Number(progress.items_completed ?? 0)
  const percent = total ? Math.round((completed / total) * 100) : null
  const elapsed = formatElapsed(progress.phase_started_at)
  const staleSeconds = ageSeconds(progress.last_progress_at)
  const label = PHASE_LABELS[phase.name] || phase.name

  return (
    <div
      className="rounded-xl border p-3"
      style={{ borderColor: 'var(--border)', background: 'var(--surface-hover)' }}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-[13px]">
        <span className="font-medium">{label}</span>
        <span className="tabular-nums" style={{ color: 'var(--fg-muted)' }}>
          {completed} / {total || EMPTY} items{percent !== null ? ` · ${percent}%` : ''}
        </span>
      </div>

      <ProgressBar
        className="mt-2"
        value={percent}
        color="var(--primary)"
        aria-label={`${label} item progress`}
      />

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[13px] sm:grid-cols-4">
        <Fact label="Successful" value={progress.items_succeeded ?? 0} />
        <Fact label="Guardrail blocked" value={progress.items_guardrail_blocked ?? 0} />
        <Fact label="Failed" value={progress.items_failed ?? 0} />
        <Fact label="In flight" value={progress.items_in_flight ?? 0} />
      </dl>

      <p className="mt-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
        Elapsed {elapsed || EMPTY}
        {staleSeconds !== null ? ` · last progress ${formatAge(staleSeconds)} ago` : ''}
      </p>

      {staleSeconds !== null && staleSeconds >= STALL_SECONDS && (
        <p className="mt-1 text-[12px]" style={{ color: 'var(--warning)' }}>
          Possible stall: no benchmark item has completed for {formatAge(staleSeconds)}.
        </p>
      )}
    </div>
  )
}
