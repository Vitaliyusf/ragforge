'use client'

import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import Card, { CardHeader } from '@/components/ui/Card'
import { cn } from '@/lib/utils'
import {
  EMPTY,
  PROFILES_BY_ID,
  TERMINAL_STATUSES,
  benchmarkSpans,
  formatRunTimestamp,
  keyResult,
  statusMeta,
} from '../evalProfiles'
import { useI18n } from '@/i18n'

/** Desktop column track. Below `md` every row collapses to stacked cells. */
const COLUMNS = 'md:grid-cols-[130px_150px_minmax(0,1fr)_120px_90px_110px_auto]'

const HEADING_KEYS = [
  'evalHistory.started',
  'evalHistory.profile',
  'evalHistory.dataset',
  'evalHistory.status',
  'evalHistory.totalTime',
  'evalHistory.keyResult',
  'evalHistory.actions',
]

/**
 * Every benchmark this dataset has recorded, one row each.
 *
 * The benchmark id is not a column: it is thirty characters of noise beside
 * the six facts that actually distinguish two runs. It stays on the row as
 * a title, where it can still be read and copied when a support question
 * needs it.
 */
export default function BenchmarkHistoryTable({
  history = [],
  selectedId,
  busy,
  onSelect,
  onDownload,
}) {
  const { t } = useI18n()
  return (
    <Card padding="sm">
      <CardHeader
        className="mb-3"
        title={t('evalHistory.title')}
        description={t('evalHistory.description')}
      />

      {history.length === 0 ? (
        <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
          {t('evalHistory.empty')}
        </p>
      ) : (
        <div role="table" aria-label={t('evalHistory.title')}>
          <div
            role="row"
            className={cn('hidden gap-x-4 border-b px-2 pb-2 md:grid', COLUMNS)}
            style={{ borderColor: 'var(--border)' }}
          >
            {HEADING_KEYS.map((headingKey) => (
              <span key={headingKey} role="columnheader" className="label-xs">
                {t(headingKey)}
              </span>
            ))}
          </div>

          {history.map((run) => {
            const status = statusMeta(run.status, t)
            const terminal = TERMINAL_STATUSES.has(run.status)
            const current = run.benchmark_id === selectedId
            // Two different clocks used to meet in this row: the column
            // said "Started" and showed creation time, while the duration
            // beside it measured execution only. A row whose two numbers
            // cannot be subtracted from each other is worse than no row.
            const started = run.started_at ? formatRunTimestamp(run.started_at) : null
            const queued = run.created_at ? formatRunTimestamp(run.created_at) : null
            // A run that has not started has no start time to show. It says
            // when it was queued, in those words, rather than passing its
            // creation time off as the thing the column is named after.
            const startedLabel =
              started || (queued ? t('evalHistory.queuedAt', { time: queued }) : EMPTY)
            const name = run.dataset_name || run.dataset?.name || t('evalHistory.goldenSet')
            // Names the run in a way a person can act on: two "View" buttons
            // in a list are indistinguishable to anyone not looking at the
            // row they sit in.
            const rowName = t('evalHistory.rowName', {
              profile: PROFILES_BY_ID[run.profile]?.labelKey
                ? t(PROFILES_BY_ID[run.profile].labelKey)
                : run.profile || t('evalModel.benchmark'),
              time: startedLabel,
            })

            return (
              <div
                key={run.benchmark_id}
                role="row"
                title={run.benchmark_id}
                className={cn(
                  'grid gap-x-4 gap-y-1 rounded-lg border-b px-2 py-2.5 text-[13px] last:border-b-0 md:items-center',
                  COLUMNS
                )}
                style={{
                  borderColor: 'var(--border)',
                  background: current ? 'var(--surface-hover)' : 'transparent',
                }}
              >
                <span role="cell" className="tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                  {startedLabel}
                </span>
                <span role="cell" className="truncate" style={{ color: 'var(--fg)' }}>
                  {PROFILES_BY_ID[run.profile]?.labelKey
                    ? t(PROFILES_BY_ID[run.profile].labelKey)
                    : run.profile || EMPTY}
                </span>
                <span role="cell" className="truncate" style={{ color: 'var(--fg-muted)' }}>
                  {name}
                  {run.dataset_version ? ` · v${run.dataset_version}` : ''}
                </span>
                <span role="cell">
                  <Badge variant={status.variant} icon={status.icon} spin={status.spin}>
                    {status.label}
                  </Badge>
                </span>
                <span role="cell" className="tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                  {benchmarkSpans(run).total}
                </span>
                <span role="cell" className="tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                  {keyResult(run)}
                </span>
                <span role="cell" className="flex flex-wrap gap-1.5 md:justify-end">
                  <Button
                    variant={current ? 'secondary' : 'ghost'}
                    size="xs"
                    disabled={busy || current}
                    aria-label={`View ${rowName}`}
                    onClick={() => onSelect(run.benchmark_id)}
                  >
                    View
                  </Button>
                  {terminal && (
                    <Button
                      variant="ghost"
                      size="xs"
                      disabled={busy}
                      aria-label={`Download ${rowName}`}
                      onClick={() => onDownload(run.benchmark_id)}
                    >
                      Download
                    </Button>
                  )}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </Card>
  )
}
