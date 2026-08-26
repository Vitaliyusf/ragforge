'use client'

import { ChevronRight, Download } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import Card, { CardHeader } from '@/components/ui/Card'
import ProgressBar from '@/components/ui/ProgressBar'
import BenchmarkComparison from '@/features/metrics/components/benchmark/BenchmarkComparison'
import {
  EMPTY,
  PHASE_LABELS,
  PHASE_SHORT_LABELS,
  PROFILES_BY_ID,
  STALL_SECONDS,
  TERMINAL_NOTES,
  ageSeconds,
  formatAge,
  formatElapsed,
  formatMetric,
  formatRunTimestamp,
  isTerminal,
  measuredPhases,
  phaseStatusMeta,
  statusMeta,
} from '../evalProfiles'

/**
 * The run itself: what it is doing now, or what it did.
 *
 * Every number here is the server's own persisted progress. Nothing is
 * interpolated on the client — a progress bar that keeps moving while the
 * backend has stopped is worse than no progress bar.
 */
export default function ActiveRunPanel({ benchmark, history = [], busy, onDownload }) {
  if (!benchmark?.benchmark_id) return null

  const status = statusMeta(benchmark.status)
  const phases = benchmark.phases || []
  const progress = benchmark.progress || {}
  const terminal = isTerminal(benchmark)
  const activePhase = phases.find((phase) => phase.status === 'running')
  const measured = measuredPhases(benchmark)
  const executableTotal =
    progress.executable_phases ??
    progress.total_phases ??
    phases.filter((phase) => phase.status !== 'unsupported').length
  const completedPhases = progress.completed_phases ?? 0
  const profileLabel = PROFILES_BY_ID[benchmark.profile]?.label || benchmark.profile

  return (
    <Card>
      <CardHeader
        title={terminal ? 'Latest run' : 'Active run'}
        description={
          `${completedPhases} / ${executableTotal} executable phases complete` +
          (profileLabel ? ` · ${profileLabel}` : '') +
          ` · started ${formatRunTimestamp(benchmark.started_at || benchmark.created_at)}`
        }
        action={
          terminal && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onDownload()}
              disabled={busy}
              leftIcon={<Download size={13} />}
            >
              Download Diagnostic ZIP
            </Button>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={status.variant} icon={status.icon} spin={status.spin}>
          {status.label}
        </Badge>
        {!terminal && (
          <span className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
            Safe to leave this page. The benchmark runs on the server and progress is saved
            automatically.
          </span>
        )}
      </div>

      {terminal && (
        <TerminalNote status={benchmark.status} error={benchmark.error} />
      )}

      {phases.length > 0 && <PhaseStepper phases={phases} />}

      {activePhase && (
        <PhaseProgress
          phase={activePhase}
          progress={activePhase.item_progress || {}}
          total={progress.items_per_phase ?? 0}
        />
      )}

      {measured.length > 0 && (
        <dl className="mt-4 grid gap-2 text-[13px] sm:grid-cols-2">
          {measured.map((phase) => (
            <div
              key={phase.name}
              className="rounded-xl border px-3 py-2"
              style={{ borderColor: 'var(--border)' }}
            >
              <dt className="label-xs">{PHASE_LABELS[phase.name] || phase.name}</dt>
              <dd className="mt-0.5 tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                MRR {formatMetric(phase.results?.mrr)} · mean latency{' '}
                {formatMetric(phase.results?.mean_latency_ms, ' ms')}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <BenchmarkComparison candidate={benchmark} history={history} />
    </Card>
  )
}

/**
 * What a terminal state means, in words as well as in colour.
 *
 * A failed run still names its error here rather than only in an archive
 * nobody has downloaded yet.
 */
function TerminalNote({ status, error }) {
  const meta = statusMeta(status)
  const Icon = meta.icon
  const tone = TONES[meta.variant] || TONES.default
  const note = TERMINAL_NOTES[status]
  if (!note && !error) return null

  return (
    <div
      className="mt-3 rounded-xl px-3 py-2.5 text-[13px]"
      style={{ background: tone.soft, border: `1px solid ${tone.border}`, color: tone.fg }}
    >
      <p className="flex items-center gap-2 font-medium">
        <Icon size={14} aria-hidden="true" />
        {meta.label}
      </p>
      {note && <p className="mt-1">{note}</p>}
      {error && <p className="mt-1 font-mono text-[12px]">{error}</p>}
    </div>
  )
}

/**
 * State colours, taken from the tokens the rest of the app already uses.
 *
 * The border is the soft fill rather than a fourth opacity of the accent:
 * one bordered rectangle per state is enough, and a saturated outline
 * around a whole paragraph reads as an alarm even when the run succeeded.
 */
const TONES = {
  success: { fg: 'var(--success)', soft: 'var(--success-soft)', border: 'transparent' },
  warning: { fg: 'var(--warning)', soft: 'var(--warning-soft)', border: 'transparent' },
  danger: { fg: 'var(--danger)', soft: 'var(--danger-soft)', border: 'transparent' },
  accent: { fg: 'var(--accent)', soft: 'var(--accent-soft)', border: 'transparent' },
  default: { fg: 'var(--fg-muted)', soft: 'var(--surface-hover)', border: 'var(--border)' },
}

/**
 * The profile's phases, in order, each with its own state.
 *
 * The list is the benchmark's own, so only the phases this profile plans
 * appear. `unsupported` renders muted and says "Not supported": it did not
 * fail, and reading it as a failure is the misdiagnosis this stepper exists
 * to prevent.
 */
function PhaseStepper({ phases }) {
  return (
    <ol className="mt-4 flex flex-wrap items-center gap-x-1 gap-y-2" aria-label="Benchmark phases">
      {phases.map((phase, index) => {
        const meta = phaseStatusMeta(phase.status)
        const Icon = meta.icon
        const detail = phase.reason || phase.error
        return (
          <li key={phase.name} className="flex items-center gap-1">
            <span
              className="flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[13px]"
              style={{ borderColor: 'var(--border)', background: 'var(--surface-hover)' }}
              title={detail || undefined}
            >
              <Icon
                size={13}
                aria-hidden="true"
                className={meta.spin ? 'animate-spin' : undefined}
                style={{ color: (TONES[meta.variant] || TONES.default).fg }}
              />
              <span style={{ color: 'var(--fg)' }}>
                {PHASE_SHORT_LABELS[phase.name] || phase.name}
              </span>
              <span style={{ color: 'var(--fg-soft)' }}>{meta.label}</span>
            </span>
            {index < phases.length - 1 && (
              <ChevronRight size={13} aria-hidden="true" style={{ color: 'var(--fg-soft)' }} />
            )}
          </li>
        )
      })}
    </ol>
  )
}

/**
 * Item-level progress for the phase that is executing.
 *
 * The denominator is the benchmark's items-per-phase: the per-phase
 * counters carry outcomes only, and every executable phase scores the whole
 * dataset. With no denominator the bar renders empty rather than guessing.
 */
function PhaseProgress({ phase, progress, total: itemsPerPhase }) {
  const total = Number(itemsPerPhase ?? 0)
  const completed = Number(progress.items_completed ?? 0)
  const percent = total ? Math.round((completed / total) * 100) : null
  const elapsed = formatElapsed(progress.phase_started_at)
  const staleSeconds = ageSeconds(progress.last_progress_at)

  return (
    <div
      className="mt-4 rounded-xl border p-3"
      style={{ borderColor: 'var(--border)', background: 'var(--surface-hover)' }}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2 text-[13px]">
        <span className="font-medium">{PHASE_LABELS[phase.name] || phase.name}</span>
        <span className="tabular-nums" style={{ color: 'var(--fg-muted)' }}>
          {completed} / {total || EMPTY} items{percent !== null ? ` · ${percent}%` : ''}
        </span>
      </div>

      <ProgressBar
        className="mt-2"
        value={percent}
        color="var(--primary)"
        aria-label={`${PHASE_LABELS[phase.name] || phase.name} item progress`}
      />

      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-[13px] sm:grid-cols-4">
        <Counter label="Successful" value={progress.items_succeeded ?? 0} />
        <Counter label="Guardrail blocked" value={progress.items_guardrail_blocked ?? 0} />
        <Counter label="Failed" value={progress.items_failed ?? 0} />
        <Counter label="In flight" value={progress.items_in_flight ?? 0} />
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

function Counter({ label, value }) {
  return (
    <div>
      <dt className="label-xs">{label}</dt>
      <dd className="mt-0.5 font-semibold tabular-nums">{value}</dd>
    </div>
  )
}
