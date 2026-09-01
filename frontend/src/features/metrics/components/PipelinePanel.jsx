'use client'

import { AlertTriangle, Workflow } from 'lucide-react'
import Button from '@/components/ui/Button'
import Card, { CardHeader } from '@/components/ui/Card'
import EmptyState from '@/components/feedback/EmptyState'
import ProgressBar from '@/components/ui/ProgressBar'
import TabSkeleton from '@/components/ui/TabSkeleton'
import DeepLink from '@/components/observability/DeepLink'
import { documentLink } from '@/lib/observability/deepLinks'
import {
  EMPTY,
  FUNNEL_STEP_LABELS,
  METRIC_LABELS,
  PROM_UNAVAILABLE,
  STAGE_LABELS,
  formatCost,
  formatCount,
  formatDecimal,
  formatPercent,
  formatSeconds,
  labelFor,
  thresholdVariant,
} from './metricsConfig'
import { intlLocale } from '@/lib/formatting/datetime'
import { useI18n } from '@/i18n'

const VARIANT_COLORS = {
  default: 'var(--fg)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  danger: 'var(--danger)',
}

/** `{key: value}` into sorted rows, largest first. */
function toRows(map) {
  return Object.entries(map || {})
    .filter(([, value]) => Number.isFinite(Number(value)))
    .map(([key, value]) => ({ key, value: Number(value) }))
    .sort((a, b) => b.value - a.value)
}

/**
 * Wrap one Prometheus-backed widget.
 *
 * The unavailable state is per widget, never per panel: a monitoring outage
 * must not blank the MongoDB-backed figures rendered beside it.
 */
function PromWidget({ promAvailable, children }) {
  const { t } = useI18n()
  if (promAvailable) return children
  return (
    <EmptyState
      icon={AlertTriangle}
      size="sm"
      title={t(PROM_UNAVAILABLE.titleKey)}
      description={t(PROM_UNAVAILABLE.descriptionKey)}
    />
  )
}

function Stat({ label, value, hint, variant = 'default' }) {
  return (
    <div>
      <dt className="label-xs">{label}</dt>
      <dd
        className="mt-0.5 text-lg font-semibold tabular-nums"
        style={{ color: VARIANT_COLORS[variant] || VARIANT_COLORS.default }}
      >
        {value}
      </dd>
      {hint && (
        <p className="mt-0.5 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
          {hint}
        </p>
      )}
    </div>
  )
}

/**
 * Ingestion-pipeline panel.
 *
 * The funnel is MongoDB-backed and tenant-scoped; stage timings, embedding
 * throughput, Kafka lag and DLQ rates come from Prometheus and are
 * platform-wide. Vector counts are collection-wide for the same reason: the
 * store is asked for the size of a collection, which no tenant filter narrows.
 *
 * Every cost shown here is an estimate derived from a static price table, and
 * is labelled as one at the figure, not only in the section heading.
 */
export default function PipelinePanel({ data, loading, error, promAvailable = true, onRetry }) {
  const { locale, t } = useI18n()
  const note = t('meta.platformScopeNote')
  if (loading && !data) return <TabSkeleton />

  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title={t('pipelinePanel.loadFailed')}
        description={error}
        action={onRetry ? <Button onClick={onRetry}>{t('common.retry')}</Button> : undefined}
      />
    )
  }

  const ingestion = data?.ingestion || {}
  const funnel = ingestion.funnel || {}
  const steps = funnel.funnel_steps || []
  const funnelFiles = funnel.files || 0
  const stuck = ingestion.stuck_files || {}
  const stuckCount = stuck.count || 0

  // Empty only when this tenant has nothing in the window *and* nothing stuck.
  // `stuck_files` is deliberately not window-scoped — a file wedged since last
  // week is the most interesting thing on the page, and hiding it behind a
  // quiet 1h window would defeat the point of collecting it.
  if (!data || (!funnelFiles && !stuckCount)) {
    return (
      <EmptyState
        icon={Workflow}
        title={t('pipelinePanel.noActivity')}
        description={t('pipelinePanel.noActivityDescription')}
      />
    )
  }

  const cost = data.cost || {}
  const unpriced = (cost.models_without_pricing || []).filter(Boolean)
  const stageRows = toRows(data.file_processing_p95_seconds)
  const lagRows = (data.kafka_consumer_lag || []).filter((row) => Number.isFinite(Number(row?.value)))
  const dlqRows = (data.dlq_rate || []).filter((row) => Number(row?.value) > 0)
  const collections = data.vectors?.collections || []
  const growth = data.vectors?.growth || {}
  const durations = ingestion.task_durations || {}

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader
          title={t('pipelinePanel.funnel')}
          description={t('pipelinePanel.funnelDescription', {
            count: formatCount(funnelFiles),
          })}
        />
        {steps.length ? (
          <ul className="flex flex-col gap-3">
            {steps.map((step) => (
              <li key={step.step}>
                <div className="mb-1 flex items-baseline justify-between gap-3">
                  <span className="text-[13px] font-medium" style={{ color: 'var(--fg)' }}>
                    {labelFor(FUNNEL_STEP_LABELS, step.step)}
                  </span>
                  <span className="text-[13px] tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                    {formatCount(step.count)}
                    {/* A null drop_off means the previous step was empty, and
                        renders as EMPTY rather than a confident 0%. The server
                        computes it so two clients cannot derive it two ways. */}
                    {step.dropped == null ? null : (
                      <span style={{ color: 'var(--fg-soft)' }}>
                        {'  '}&minus;{formatCount(step.dropped)} (
                        {step.drop_off == null ? EMPTY : formatPercent(step.drop_off)})
                      </span>
                    )}
                  </span>
                </div>
                <ProgressBar
                  value={step.share_of_uploaded == null ? null : step.share_of_uploaded * 100}
                  color="var(--primary)"
                  thickness="md"
                  aria-label={t('pipelinePanel.funnelStepAria', {
                    step: labelFor(FUNNEL_STEP_LABELS, step.step),
                    count: formatCount(step.count),
                  })}
                />
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={Workflow}
            size="sm"
            title={t('pipelinePanel.noFunnelData')}
            description={t('pipelinePanel.noFunnelDataDescription')}
          />
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            title={t('pipelinePanel.perStage')}
            description={t('pipelinePanel.perStageDescription', { note })}
          />
          <PromWidget promAvailable={promAvailable}>
            {stageRows.length ? (
              <table className="w-full text-[13px]">
                <caption className="sr-only">{t('pipelinePanel.perStageCaption')}</caption>
                <thead>
                  <tr style={{ color: 'var(--fg-muted)' }}>
                    <th scope="col" className="py-1.5 text-start font-medium">{t('pipelinePanel.stage')}</th>
                    <th scope="col" className="py-1.5 text-end font-medium">p95</th>
                  </tr>
                </thead>
                <tbody>
                  {stageRows.map((row) => (
                    <tr key={row.key} className="border-t" style={{ borderColor: 'var(--border)' }}>
                      <th
                        scope="row"
                        className="py-1.5 text-start font-normal"
                        style={{ color: 'var(--fg)' }}
                      >
                        {labelFor(STAGE_LABELS, row.key)}
                      </th>
                      <td className="py-1.5 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                        {formatSeconds(row.value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState
                icon={Workflow}
                size="sm"
                title={t('pipelinePanel.noStageTimings')}
                description={t('pipelinePanel.noStageTimingsDescription')}
              />
            )}
          </PromWidget>
        </Card>

        <Card>
          <CardHeader
            title={t('pipelinePanel.wholeTask')}
            description={t('pipelinePanel.wholeTaskDescription')}
          />
          <dl className="grid grid-cols-2 gap-4">
            <Stat
              label={t('pipelinePanel.tasks')}
              value={formatCount(durations.tasks)}
              hint={t('pipelinePanel.completedInWindow')}
            />
            <Stat label={t('pipelinePanel.mean')} value={formatSeconds(durations.mean_seconds)} />
            <Stat label="p95" value={formatSeconds(durations.p95_seconds)} />
            <Stat label="p99" value={formatSeconds(durations.p99_seconds)} />
          </dl>
        </Card>
      </div>

      <Card>
        <CardHeader
          title={METRIC_LABELS.stuck_files}
          description={t('pipelinePanel.stuckDescription', {
            minutes: stuck.threshold_minutes ?? EMPTY,
          })}
        />
        {stuckCount ? (
          <>
            <dl className="mb-3 grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Stat
                label={t('pipelinePanel.stuckFiles')}
                value={formatCount(stuckCount)}
                hint={t(stuck.truncated
                  ? 'pipelinePanel.listTruncated'
                  : 'pipelinePanel.allListedBelow')}
                variant={thresholdVariant(stuckCount, 'stuck_files')}
              />
            </dl>
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <caption className="sr-only">{t('pipelinePanel.stuckCaption')}</caption>
                <thead>
                  <tr style={{ color: 'var(--fg-muted)' }}>
                    <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('pipelinePanel.file')}</th>
                    <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('common.status')}</th>
                    <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('pipelinePanel.lastUpdated')}</th>
                    <th scope="col" className="py-1.5 text-start font-medium">
                      <span className="sr-only">{t('pipelinePanel.openDocument')}</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {(stuck.files || []).map((file) => (
                    <tr
                      key={file.file_id || file.filename}
                      className="border-t"
                      style={{ borderColor: 'var(--border)' }}
                    >
                      {/* A filename is user data and reads in its own
                          direction; the id fallback beside it does not. */}
                      <th
                        scope="row"
                        dir="auto"
                        className="max-w-[20rem] truncate py-1.5 pe-3 text-start font-normal"
                        style={{ color: 'var(--fg)' }}
                        title={file.file_id}
                      >
                        {file.filename || file.file_id || EMPTY}
                      </th>
                      <td className="py-1.5 pe-3" style={{ color: 'var(--fg-muted)' }}>
                        {file.status || EMPTY}
                      </td>
                      <td className="py-1.5 pe-3" style={{ color: 'var(--fg-muted)' }}>
                        {file.updated_at
                          ? new Date(file.updated_at).toLocaleString(intlLocale(locale))
                          : EMPTY}
                      </td>
                      {/* A wedged file is only actionable where it can be
                          retried or deleted, which is Knowledge. */}
                      <td className="py-1.5">
                        <DeepLink link={documentLink(file.file_id, file.filename)} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          /* The healthy case. Deliberately plain: no icon, no warning colour —
             an empty stuck-list is good news and must not look like an alert. */
          <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
            {t('pipelinePanel.nothingStuck', { minutes: stuck.threshold_minutes ?? EMPTY })}
          </p>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            title={t('pipelinePanel.embeddingThroughput')}
            description={t('pipelinePanel.embeddingDescription', { note })}
          />
          <PromWidget promAvailable={promAvailable}>
            <dl className="grid grid-cols-2 gap-4">
              <Stat
                label={METRIC_LABELS.embedding_chunk_rate}
                value={formatDecimal(data.embedding_chunk_rate)}
                hint={t('pipelinePanel.chunksPerSecond')}
              />
              <Stat
                label={t('pipelinePanel.embeddingP95')}
                value={formatSeconds(data.embedding_p95_seconds)}
              />
            </dl>
          </PromWidget>
        </Card>

        <Card>
          <CardHeader
            title={METRIC_LABELS.vectors}
            description={t('pipelinePanel.vectorsDescription', { note })}
          />
          {collections.length ? (
            <table className="w-full text-[13px]">
              <caption className="sr-only">{t('pipelinePanel.vectorsCaption')}</caption>
              <thead>
                <tr style={{ color: 'var(--fg-muted)' }}>
                  <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('pipelinePanel.collection')}</th>
                  <th scope="col" className="py-1.5 pe-3 text-end font-medium">{t('pipelinePanel.vectors')}</th>
                  <th scope="col" className="py-1.5 text-end font-medium">{t('pipelinePanel.added')}</th>
                </tr>
              </thead>
              <tbody>
                {collections.map((row) => (
                  <tr key={row.collection} className="border-t" style={{ borderColor: 'var(--border)' }}>
                    <th
                      scope="row"
                      dir="ltr"
                      className="py-1.5 pe-3 text-start font-normal [unicode-bidi:isolate]"
                      style={{ color: 'var(--fg)' }}
                    >
                      {row.collection || EMPTY}
                    </th>
                    <td className="py-1.5 pe-3 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatCount(row.vectors)}
                    </td>
                    <td className="py-1.5 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {promAvailable ? formatCount(growth[row.collection]) : EMPTY}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState
              icon={Workflow}
              size="sm"
              title={t('pipelinePanel.noCollectionCounts')}
              description={t('pipelinePanel.noCollectionCountsDescription')}
            />
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            title={METRIC_LABELS.kafka_consumer_lag}
            description={t('pipelinePanel.lagDescription', { note })}
          />
          <PromWidget promAvailable={promAvailable}>
            {lagRows.length ? (
              <table className="w-full text-[13px]">
                <caption className="sr-only">{t('pipelinePanel.lagCaption')}</caption>
                <thead>
                  <tr style={{ color: 'var(--fg-muted)' }}>
                    <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('pipelinePanel.topic')}</th>
                    <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('pipelinePanel.group')}</th>
                    <th scope="col" className="py-1.5 text-end font-medium">{t('pipelinePanel.lag')}</th>
                  </tr>
                </thead>
                <tbody>
                  {lagRows.map((row) => (
                    <tr
                      key={`${row.topic}-${row.group}`}
                      className="border-t"
                      style={{ borderColor: 'var(--border)' }}
                    >
                      <th
                        scope="row"
                        dir="ltr"
                        className="py-1.5 pe-3 text-start font-normal [unicode-bidi:isolate]"
                        style={{ color: 'var(--fg)' }}
                      >
                        {row.topic || EMPTY}
                      </th>
                      <td className="py-1.5 pe-3" style={{ color: 'var(--fg-muted)' }}>
                        {row.group || EMPTY}
                      </td>
                      <td
                        className="py-1.5 text-end tabular-nums font-medium"
                        style={{ color: VARIANT_COLORS[thresholdVariant(row.value, 'kafka_consumer_lag')] }}
                      >
                        {formatCount(row.value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              /* No series is "no consumer has fetched yet", not a lag of zero.
                 Said plainly rather than drawn as a healthy 0. */
              <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
                {t('pipelinePanel.noOffsetReported')}
              </p>
            )}
          </PromWidget>
        </Card>

        <Card>
          <CardHeader
            title={t('pipelinePanel.dlq')}
            description={t('pipelinePanel.dlqDescription', { note })}
          />
          <PromWidget promAvailable={promAvailable}>
            {dlqRows.length ? (
              <table className="w-full text-[13px]">
                <caption className="sr-only">{t('pipelinePanel.dlqCaption')}</caption>
                <thead>
                  <tr style={{ color: 'var(--fg-muted)' }}>
                    <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('pipelinePanel.service')}</th>
                    <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('pipelinePanel.error')}</th>
                    <th scope="col" className="py-1.5 text-end font-medium">{t('pipelinePanel.perSecond')}</th>
                  </tr>
                </thead>
                <tbody>
                  {dlqRows.map((row) => (
                    <tr
                      key={`${row.service}-${row.error_type}`}
                      className="border-t"
                      style={{ borderColor: 'var(--border)' }}
                    >
                      <th
                        scope="row"
                        dir="ltr"
                        className="py-1.5 pe-3 text-start font-normal [unicode-bidi:isolate]"
                        style={{ color: 'var(--fg)' }}
                      >
                        {row.service || EMPTY}
                      </th>
                      <td className="py-1.5 pe-3" style={{ color: 'var(--fg-muted)' }}>
                        {row.error_type || EMPTY}
                      </td>
                      <td
                        className="py-1.5 text-end tabular-nums"
                        style={{ color: 'var(--danger)' }}
                      >
                        {formatDecimal(row.value)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
                {t('pipelinePanel.noDlq')}
              </p>
            )}
          </PromWidget>
        </Card>
      </div>

      <Card>
        <CardHeader
          title={t('pipelinePanel.cost')}
          description={t('pipelinePanel.costNote')}
        />
        <dl className="mb-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat label={t('pipelinePanel.tokensIn')} value={formatCount(cost.tokens_in)} />
          <Stat label={t('pipelinePanel.tokensOut')} value={formatCount(cost.tokens_out)} />
          <Stat
            label={METRIC_LABELS.estimated_cost_usd}
            value={formatCost(cost.estimated_cost_usd)}
            hint={t('pipelinePanel.estimate')}
          />
        </dl>

        {unpriced.length > 0 && (
          <p className="mb-3 text-[12px]" style={{ color: 'var(--warning)' }}>
            {t('pipelinePanel.unpricedModels', { models: unpriced.join(', ') })}
          </p>
        )}

        {(cost.by_model || []).length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <caption className="sr-only">{t('pipelinePanel.costCaption')}</caption>
              <thead>
                <tr style={{ color: 'var(--fg-muted)' }}>
                  <th scope="col" className="py-1.5 pe-3 text-start font-medium">{t('pipelinePanel.model')}</th>
                  <th scope="col" className="py-1.5 pe-3 text-end font-medium">{t('pipelinePanel.turns')}</th>
                  <th scope="col" className="py-1.5 pe-3 text-end font-medium">{t('pipelinePanel.tokensIn')}</th>
                  <th scope="col" className="py-1.5 pe-3 text-end font-medium">{t('pipelinePanel.tokensOut')}</th>
                  <th scope="col" className="py-1.5 text-end font-medium">{t('pipelinePanel.estimatedCost')}</th>
                </tr>
              </thead>
              <tbody>
                {cost.by_model.map((row) => (
                  <tr key={row.model || 'unknown'} className="border-t" style={{ borderColor: 'var(--border)' }}>
                    {/* A model id is a repository slug: never reordered. */}
                    <th
                      scope="row"
                      dir="ltr"
                      className="max-w-[18rem] truncate py-1.5 pe-3 text-start font-normal [unicode-bidi:isolate]"
                      style={{ color: 'var(--fg)' }}
                      title={row.model}
                    >
                      {row.model || EMPTY}
                    </th>
                    <td className="py-1.5 pe-3 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatCount(row.turns)}
                    </td>
                    <td className="py-1.5 pe-3 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatCount(row.tokens_in)}
                    </td>
                    <td className="py-1.5 pe-3 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatCount(row.tokens_out)}
                    </td>
                    <td className="py-1.5 text-end tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatCost(row.estimated_cost_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
            {t('pipelinePanel.noModelUsage')}
          </p>
        )}

        {/* One row, always: the metrics API refuses cross-tenant reads, so this
            is the caller's own tenant and never a comparison between tenants. */}
        {(cost.by_tenant || []).length > 0 && (
          <p className="mt-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
            {t('pipelinePanel.singleTenantNote', {
              tenant: cost.by_tenant[0].tenant_id || EMPTY,
            })}
          </p>
        )}
      </Card>
    </div>
  )
}
