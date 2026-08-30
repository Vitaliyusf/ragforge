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
  COST_ESTIMATE_NOTE,
  EMPTY,
  FUNNEL_STEP_LABELS,
  METRIC_LABELS,
  PLATFORM_SCOPE_NOTE,
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
  if (promAvailable) return children
  return (
    <EmptyState
      icon={AlertTriangle}
      size="sm"
      title={PROM_UNAVAILABLE.title}
      description={PROM_UNAVAILABLE.description}
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
  if (loading && !data) return <TabSkeleton />

  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Could not load pipeline metrics"
        description={error}
        action={onRetry ? <Button onClick={onRetry}>Retry</Button> : undefined}
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
        title="No ingestion activity"
        description="No files were uploaded in this window, and none are stuck in processing."
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
          title="Ingestion funnel"
          description={`Where files are lost between upload and index. ${formatCount(
            funnelFiles
          )} files entered this window.`}
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
                  aria-label={`${labelFor(FUNNEL_STEP_LABELS, step.step)}: ${formatCount(
                    step.count
                  )} files`}
                />
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={Workflow}
            size="sm"
            title="No funnel data"
            description="No files were uploaded in this window."
          />
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Per-stage duration"
            description={`Ingestion stage p95. ${PLATFORM_SCOPE_NOTE}`}
          />
          <PromWidget promAvailable={promAvailable}>
            {stageRows.length ? (
              <table className="w-full text-[13px]">
                <caption className="sr-only">Ingestion stage p95 duration</caption>
                <thead>
                  <tr style={{ color: 'var(--fg-muted)' }}>
                    <th scope="col" className="py-1.5 text-left font-medium">Stage</th>
                    <th scope="col" className="py-1.5 text-right font-medium">p95</th>
                  </tr>
                </thead>
                <tbody>
                  {stageRows.map((row) => (
                    <tr key={row.key} className="border-t" style={{ borderColor: 'var(--border)' }}>
                      <th
                        scope="row"
                        className="py-1.5 text-left font-normal"
                        style={{ color: 'var(--fg)' }}
                      >
                        {labelFor(STAGE_LABELS, row.key)}
                      </th>
                      <td className="py-1.5 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
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
                title="No stage timings"
                description="Prometheus recorded no ingestion stages in this window."
              />
            )}
          </PromWidget>
        </Card>

        <Card>
          <CardHeader
            title="Whole-task duration"
            description="Upload to completion, from the metrics store."
          />
          <dl className="grid grid-cols-2 gap-4">
            <Stat label="Tasks" value={formatCount(durations.tasks)} hint="completed in window" />
            <Stat label="Mean" value={formatSeconds(durations.mean_seconds)} />
            <Stat label="p95" value={formatSeconds(durations.p95_seconds)} />
            <Stat label="p99" value={formatSeconds(durations.p99_seconds)} />
          </dl>
        </Card>
      </div>

      <Card>
        <CardHeader
          title={METRIC_LABELS.stuck_files}
          description={`Files in flight longer than ${stuck.threshold_minutes ?? EMPTY} minutes. Not window-scoped — a file stuck since last week still appears.`}
        />
        {stuckCount ? (
          <>
            <dl className="mb-3 grid grid-cols-2 gap-4 lg:grid-cols-4">
              <Stat
                label="Stuck files"
                value={formatCount(stuckCount)}
                hint={stuck.truncated ? 'list truncated' : 'all listed below'}
                variant={thresholdVariant(stuckCount, 'stuck_files')}
              />
            </dl>
            <div className="overflow-x-auto">
              <table className="w-full text-[13px]">
                <caption className="sr-only">Files stuck in an in-flight status</caption>
                <thead>
                  <tr style={{ color: 'var(--fg-muted)' }}>
                    <th scope="col" className="py-1.5 pr-3 text-left font-medium">File</th>
                    <th scope="col" className="py-1.5 pr-3 text-left font-medium">Status</th>
                    <th scope="col" className="py-1.5 pr-3 text-left font-medium">Last updated</th>
                    <th scope="col" className="py-1.5 text-left font-medium">
                      <span className="sr-only">Open the document</span>
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
                      <th
                        scope="row"
                        className="max-w-[20rem] truncate py-1.5 pr-3 text-left font-normal"
                        style={{ color: 'var(--fg)' }}
                        title={file.file_id}
                      >
                        {file.filename || file.file_id || EMPTY}
                      </th>
                      <td className="py-1.5 pr-3" style={{ color: 'var(--fg-muted)' }}>
                        {file.status || EMPTY}
                      </td>
                      <td className="py-1.5 pr-3" style={{ color: 'var(--fg-muted)' }}>
                        {file.updated_at ? new Date(file.updated_at).toLocaleString() : EMPTY}
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
            Nothing has been in flight longer than {stuck.threshold_minutes ?? EMPTY} minutes.
          </p>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            title="Embedding throughput"
            description={`Chunks embedded per second, and embedding latency. ${PLATFORM_SCOPE_NOTE}`}
          />
          <PromWidget promAvailable={promAvailable}>
            <dl className="grid grid-cols-2 gap-4">
              <Stat
                label={METRIC_LABELS.embedding_chunk_rate}
                value={formatDecimal(data.embedding_chunk_rate)}
                hint="chunks/sec"
              />
              <Stat label="Embedding p95" value={formatSeconds(data.embedding_p95_seconds)} />
            </dl>
          </PromWidget>
        </Card>

        <Card>
          <CardHeader
            title={METRIC_LABELS.vectors}
            description={`Points per collection, and what this window added. ${PLATFORM_SCOPE_NOTE}`}
          />
          {collections.length ? (
            <table className="w-full text-[13px]">
              <caption className="sr-only">Vector count and growth by collection</caption>
              <thead>
                <tr style={{ color: 'var(--fg-muted)' }}>
                  <th scope="col" className="py-1.5 pr-3 text-left font-medium">Collection</th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-medium">Vectors</th>
                  <th scope="col" className="py-1.5 text-right font-medium">Added</th>
                </tr>
              </thead>
              <tbody>
                {collections.map((row) => (
                  <tr key={row.collection} className="border-t" style={{ borderColor: 'var(--border)' }}>
                    <th
                      scope="row"
                      className="py-1.5 pr-3 text-left font-normal"
                      style={{ color: 'var(--fg)' }}
                    >
                      {row.collection || EMPTY}
                    </th>
                    <td className="py-1.5 pr-3 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatCount(row.vectors)}
                    </td>
                    <td className="py-1.5 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
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
              title="No collection counts"
              description="The vector service did not report collection sizes."
            />
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader
            title={METRIC_LABELS.kafka_consumer_lag}
            description={`Messages a consumer group is behind. ${PLATFORM_SCOPE_NOTE}`}
          />
          <PromWidget promAvailable={promAvailable}>
            {lagRows.length ? (
              <table className="w-full text-[13px]">
                <caption className="sr-only">Kafka consumer lag by topic and group</caption>
                <thead>
                  <tr style={{ color: 'var(--fg-muted)' }}>
                    <th scope="col" className="py-1.5 pr-3 text-left font-medium">Topic</th>
                    <th scope="col" className="py-1.5 pr-3 text-left font-medium">Group</th>
                    <th scope="col" className="py-1.5 text-right font-medium">Lag</th>
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
                        className="py-1.5 pr-3 text-left font-normal"
                        style={{ color: 'var(--fg)' }}
                      >
                        {row.topic || EMPTY}
                      </th>
                      <td className="py-1.5 pr-3" style={{ color: 'var(--fg-muted)' }}>
                        {row.group || EMPTY}
                      </td>
                      <td
                        className="py-1.5 text-right tabular-nums font-medium"
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
                No consumer group has reported an offset yet.
              </p>
            )}
          </PromWidget>
        </Card>

        <Card>
          <CardHeader
            title="Dead letter queue"
            description={`Messages failing into the DLQ, by error type. ${PLATFORM_SCOPE_NOTE}`}
          />
          <PromWidget promAvailable={promAvailable}>
            {dlqRows.length ? (
              <table className="w-full text-[13px]">
                <caption className="sr-only">Dead letter queue rate by service and error type</caption>
                <thead>
                  <tr style={{ color: 'var(--fg-muted)' }}>
                    <th scope="col" className="py-1.5 pr-3 text-left font-medium">Service</th>
                    <th scope="col" className="py-1.5 pr-3 text-left font-medium">Error</th>
                    <th scope="col" className="py-1.5 text-right font-medium">Per sec</th>
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
                        className="py-1.5 pr-3 text-left font-normal"
                        style={{ color: 'var(--fg)' }}
                      >
                        {row.service || EMPTY}
                      </th>
                      <td className="py-1.5 pr-3" style={{ color: 'var(--fg-muted)' }}>
                        {row.error_type || EMPTY}
                      </td>
                      <td
                        className="py-1.5 text-right tabular-nums"
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
                No messages reached the dead letter queue in this window.
              </p>
            )}
          </PromWidget>
        </Card>
      </div>

      <Card>
        <CardHeader title="Token usage and estimated cost" description={COST_ESTIMATE_NOTE} />
        <dl className="mb-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <Stat label="Tokens in" value={formatCount(cost.tokens_in)} />
          <Stat label="Tokens out" value={formatCount(cost.tokens_out)} />
          <Stat
            label={METRIC_LABELS.estimated_cost_usd}
            value={formatCost(cost.estimated_cost_usd)}
            hint="estimate"
          />
        </dl>

        {unpriced.length > 0 && (
          <p className="mb-3 text-[12px]" style={{ color: 'var(--warning)' }}>
            No price is configured for {unpriced.join(', ')}. Their spend counts as $0.00, which
            means unpriced, not free.
          </p>
        )}

        {(cost.by_model || []).length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <caption className="sr-only">Token usage and estimated cost by model</caption>
              <thead>
                <tr style={{ color: 'var(--fg-muted)' }}>
                  <th scope="col" className="py-1.5 pr-3 text-left font-medium">Model</th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-medium">Turns</th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-medium">Tokens in</th>
                  <th scope="col" className="py-1.5 pr-3 text-right font-medium">Tokens out</th>
                  <th scope="col" className="py-1.5 text-right font-medium">Estimated cost</th>
                </tr>
              </thead>
              <tbody>
                {cost.by_model.map((row) => (
                  <tr key={row.model || 'unknown'} className="border-t" style={{ borderColor: 'var(--border)' }}>
                    <th
                      scope="row"
                      className="max-w-[18rem] truncate py-1.5 pr-3 text-left font-normal"
                      style={{ color: 'var(--fg)' }}
                      title={row.model}
                    >
                      {row.model || EMPTY}
                    </th>
                    <td className="py-1.5 pr-3 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatCount(row.turns)}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatCount(row.tokens_in)}
                    </td>
                    <td className="py-1.5 pr-3 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatCount(row.tokens_out)}
                    </td>
                    <td className="py-1.5 text-right tabular-nums" style={{ color: 'var(--fg-muted)' }}>
                      {formatCost(row.estimated_cost_usd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
            No model usage was recorded in this window.
          </p>
        )}

        {/* One row, always: the metrics API refuses cross-tenant reads, so this
            is the caller's own tenant and never a comparison between tenants. */}
        {(cost.by_tenant || []).length > 0 && (
          <p className="mt-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
            Tenant {cost.by_tenant[0].tenant_id || EMPTY} accounts for all of it —
            this view is scoped to one tenant, so it is not a comparison.
          </p>
        )}
      </Card>
    </div>
  )
}
