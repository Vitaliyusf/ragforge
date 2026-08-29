'use client'

import { useMemo, useState } from 'react'
import { Download } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import StatCard from '@/components/ui/StatCard'
import Tabs, { TabPanel } from '@/components/ui/Tabs'
import TimeSeries from '@/features/metrics/components/charts/TimeSeries'
import {
  CONFIG_DIFF_NOTE,
  EVAL_HISTORY_K,
  FAILURE_ATTRIBUTION_NOTE,
  FILE_MATCH_NOTE,
  LABELS_VERIFIED_NOTE,
  MATCH_MODE_LABELS,
  formatCount,
  formatMs,
  formatPercent,
  labelFor,
} from '@/features/metrics/components/metricsConfig'
import { TERMINAL_NOTES } from '../../evalProfiles'
import {
  buildComparison,
  diffSnapshots,
  explainFailure,
  latencySummary,
} from '../../runReport'
import ComparisonPanel from './ComparisonPanel'
import ExecutionFlow from './ExecutionFlow'
import ItemExplorer from './ItemExplorer'
import LiveProgress from './LiveProgress'
import RunFailure from './RunFailure'
import {
  AnswerQualityDetail,
  ConfigDiff,
  ConfigSnapshot,
  DatasetProvenance,
  FailureAttribution,
  LabelValidation,
  ScoresAtK,
} from './sections'
import { Fact, Note } from './primitives'

/**
 * One run, as a report rather than a wall of cards.
 *
 * The page reads in the order somebody diagnoses a run: what this run was
 * and how it ended, which stages actually executed, the handful of numbers
 * that summarise it, and only then the evidence — behind tabs, because the
 * evidence is six tables deep and a page that renders all of it at once is
 * a page nobody reads.
 *
 * Two things are never behind a tab: a warning that the ground truth no
 * longer exists, and a failure. Both change how every number above them
 * should be read, so neither is allowed to depend on a click.
 */
export default function RunReport({
  report,
  history = [],
  runs = [],
  dataset,
  busy = false,
  onDownload,
  onRetry,
}) {
  const [tab, setTab] = useState('overview')

  const failure = useMemo(
    () =>
      report
        ? explainFailure({
            status: report.status,
            error: report.error,
            stages: report.stages,
            // The archive button lives in the header, where it is offered
            // for every terminal run; repeating it here would ask the same
            // question twice on the one screen a reader is scanning fastest.
            retryable: Boolean(onRetry) && report.terminal,
            exportable: false,
          })
        : null,
    [report, onRetry, onDownload]
  )

  const comparison = useMemo(
    () => (report?.kind === 'benchmark' ? buildComparison(report.raw, history) : null),
    [report, history]
  )

  const configDiff = useMemo(
    () =>
      report?.kind === 'evaluation' && runs.length >= 2
        ? diffSnapshots(runs[0]?.config_snapshot, runs[1]?.config_snapshot)
        : [],
    [report, runs]
  )

  const series = useMemo(
    () => (report?.kind === 'evaluation' ? historySeries(runs) : []),
    [report, runs]
  )

  if (!report) return null

  const status = report.statusMeta
  const tabs = tabsFor(report)

  return (
    <Card>
      <RunHeader report={report} busy={busy} onDownload={onDownload} />

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge variant={status.variant} icon={status.icon} spin={status.spin}>
          {status.label}
        </Badge>
        {report.terminal ? (
          // Only for a run with nothing to explain. A run that failed, was
          // interrupted or finished partially says so once, in the failure
          // block below, rather than twice in two different wordings.
          !failure &&
          TERMINAL_NOTES[report.status] && (
            <span className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
              {TERMINAL_NOTES[report.status]}
            </span>
          )
        ) : (
          <span className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
            Safe to leave this page. The run continues on the server and progress is saved
            automatically.
          </span>
        )}
      </div>

      <div className="mt-4">
        <ExecutionFlow stages={report.stages} />
      </div>

      {report.activePhase && (
        <div className="mt-4">
          <LiveProgress
            phase={report.activePhase}
            itemsPerPhase={report.progress?.items_per_phase}
          />
        </div>
      )}

      {/* Never behind a tab: a score resting on labels the index no longer
          holds, and a run that did not finish, both change how every figure
          below them reads. */}
      {(report.labelValidation || failure) && (
        <div className="mt-4 flex flex-col gap-3">
          <LabelValidation validation={report.labelValidation} />
          <RunFailure
            failure={failure}
            busy={busy}
            onRetry={onRetry}
            onDownload={onDownload}
          />
        </div>
      )}

      {report.kpis.length > 0 && (
        <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
          {report.kpis.map((kpi) => (
            <StatCard
              key={kpi.key}
              label={kpi.label}
              value={kpi.value}
              subLabel={kpi.subLabel}
              variant={kpi.variant}
            />
          ))}
        </div>
      )}

      <div className="mt-5">
        <Tabs tabs={tabs} value={tab} onChange={setTab} label={`${report.label} run report`} />

        {tab === 'overview' && (
          <TabPanel id="overview">
            <div className="flex flex-col gap-4">
              <DatasetProvenance run={report.raw} dataset={dataset} />
              {report.labelValidation?.checked && <Note>{LABELS_VERIFIED_NOTE}</Note>}
              {report.kind === 'benchmark' ? (
                <ComparisonPanel comparison={comparison} />
              ) : (
                <RecallTrend series={series} />
              )}
            </div>
          </TabPanel>
        )}

        {tab === 'retrieval' && (
          <TabPanel id="retrieval">
            <Measurements report={report} render={(measurement) => <Retrieval measurement={measurement} matchMode={report.matchMode} />} />
          </TabPanel>
        )}

        {tab === 'quality' && (
          <TabPanel id="quality">
            <Measurements
              report={report}
              render={(measurement) =>
                measurement.results?.answer_quality ? (
                  <AnswerQualityDetail quality={measurement.results.answer_quality} />
                ) : (
                  <Note>
                    This phase generated no answers, so there is nothing for the judge to score.
                  </Note>
                )
              }
            />
          </TabPanel>
        )}

        {tab === 'failures' && (
          <TabPanel id="failures">
            <p className="mb-3 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
              {FAILURE_ATTRIBUTION_NOTE}
            </p>
            <Measurements
              report={report}
              render={(measurement) =>
                measurement.results?.failure_attribution?.items_attributed > 0 ? (
                  <FailureAttribution attribution={measurement.results.failure_attribution} />
                ) : (
                  <Note>
                    No item in this phase could be attributed to a stage. A run from before
                    attribution existed records none rather than claiming zero failures.
                  </Note>
                )
              }
            />
          </TabPanel>
        )}

        {tab === 'items' && (
          <TabPanel id="items">
            <ItemsTab report={report} />
          </TabPanel>
        )}

        {tab === 'configuration' && (
          <TabPanel id="configuration">
            <div className="flex flex-col gap-4">
              {configDiff.length > 0 && (
                <div>
                  <h4 className="text-[13px] font-medium" style={{ color: 'var(--warning)' }}>
                    Configuration changed between runs
                  </h4>
                  <p className="mb-2 mt-0.5 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                    {CONFIG_DIFF_NOTE}
                  </p>
                  <ConfigDiff diff={configDiff} unobserved={runs[0]?.config_snapshot?.unobserved} />
                </div>
              )}
              <ConfigSnapshot snapshot={report.configSnapshot} />
            </div>
          </TabPanel>
        )}
      </div>
    </Card>
  )
}

/**
 * The run in human terms.
 *
 * Profile, dataset, when and how long, in that order. The id is last and
 * small: nobody recognises their run by a UUID, and putting one where the
 * name belongs is what made the old panel unreadable at a glance.
 */
function RunHeader({ report, busy, onDownload }) {
  const { dataset } = report
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h3 className="text-[15px] font-semibold" style={{ color: 'var(--fg)' }}>
          {report.label}
          <span className="ml-2 text-[13px] font-normal" style={{ color: 'var(--fg-soft)' }}>
            {report.kindLabel}
          </span>
        </h3>
        <p className="mt-0.5 text-[13px]" style={{ color: 'var(--fg-muted)' }}>
          {dataset.name}
          {dataset.version ? ` · v${dataset.version}` : ''}
          {dataset.itemCount != null ? ` · ${formatCount(dataset.itemCount)} items` : ''}
          {` · started ${report.startedLabel}`}
          {` · ${report.duration}`}
        </p>
        <p className="mt-1 text-[12px]" style={{ color: 'var(--fg-soft)' }}>
          {report.idLabel} <code className="tabular-nums">{report.id}</code>
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        {onDownload && report.terminal && (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onDownload()}
            disabled={busy}
            leftIcon={<Download size={13} />}
          >
            Download Diagnostic ZIP
          </Button>
        )}
      </div>
    </div>
  )
}

/** Which tabs this run can fill, with the counts that matter on them. */
function tabsFor(report) {
  const failed = report.primary?.results?.items_failed
  return [
    { id: 'overview', label: 'Overview' },
    { id: 'retrieval', label: 'Retrieval' },
    { id: 'quality', label: 'Quality' },
    {
      id: 'failures',
      label: 'Failures',
      badge: failed > 0 ? formatCount(failed) : null,
      tone: failed > 0 ? 'danger' : undefined,
    },
    {
      id: 'items',
      label: 'Items',
      badge: report.items?.length ? formatCount(report.items.length) : null,
    },
    { id: 'configuration', label: 'Configuration' },
  ]
}

/**
 * One block per measured phase.
 *
 * A benchmark measures the same corpus two or three times under different
 * pipelines; pooling those into one table would produce a number describing
 * no measurement anyone performed.
 */
function Measurements({ report, render }) {
  if (!report.measurements.length) {
    return <Note>This run has not measured anything yet.</Note>
  }
  if (report.measurements.length === 1) return render(report.measurements[0])
  return (
    <div className="flex flex-col gap-5">
      {report.measurements.map((measurement) => (
        <section key={measurement.key}>
          <h4 className="mb-2 text-[13px] font-medium" style={{ color: 'var(--fg)' }}>
            {measurement.label}
          </h4>
          {render(measurement)}
        </section>
      ))}
    </div>
  )
}

/** Scores at every cutoff, plus the latency the run can actually evidence. */
function Retrieval({ measurement, matchMode }) {
  const latency = latencySummary(measurement.items)
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
        {matchMode === 'file_id'
          ? FILE_MATCH_NOTE
          : `${labelFor(MATCH_MODE_LABELS, matchMode || 'chunk_id')} matching against the labelled ids.`}
      </p>
      <ScoresAtK results={measurement.results} />
      <dl className="flex flex-wrap gap-6 text-[13px]">
        <Fact label="Mean latency" value={formatMs(measurement.results?.mean_latency_ms)} />
        <Fact label="Latency p50" value={formatMs(latency.p50)} />
        <Fact label="Latency p95" value={formatMs(latency.p95)} />
        <Fact
          label="Latency sample"
          value={latency.sample ? formatCount(latency.sample) : 'no per-item rows'}
        />
      </dl>
    </div>
  )
}

/** The item view, or the reason this kind of run does not carry one. */
function ItemsTab({ report }) {
  return (
    <ItemExplorer
      items={report.items || []}
      emptyNote={
        report.kind === 'benchmark'
          ? 'A benchmark keeps its per-item rows in the diagnostic archive rather than in the record this page polls. Download the archive to inspect them.'
          : 'This run kept no per-item rows.'
      }
    />
  )
}

/**
 * Completed runs as one Recall@5 series, oldest first.
 *
 * Nothing is drawn below two points: `TimeSeries` renders null for a single
 * point — one point is not a line — so passing it one would leave an empty
 * panel where the report should be saying why there is no trend yet.
 */
function historySeries(runs) {
  const points = (runs || [])
    .filter((entry) => entry?.status === 'completed')
    .map((entry) => [
      Date.parse(entry?.started_at),
      Number(entry?.results?.recall_at_k?.[EVAL_HISTORY_K]),
    ])
    .filter(([time, value]) => Number.isFinite(time) && Number.isFinite(value))
    .sort((a, b) => a[0] - b[0])
  return points.length >= 2 ? [{ name: `Recall@${EVAL_HISTORY_K}`, points }] : []
}

function RecallTrend({ series }) {
  if (!series.length) {
    return <Note>Two completed runs are needed before a trend can be drawn.</Note>
  }
  return (
    <TimeSeries
      series={series}
      label={`Recall@${EVAL_HISTORY_K} by run`}
      yFormat={(value) => formatPercent(value)}
    />
  )
}
