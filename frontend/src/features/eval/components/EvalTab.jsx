'use client'

import { useMemo, useState } from 'react'
import { AlertTriangle, FlaskConical, RefreshCw, Upload } from 'lucide-react'
import Button from '@/components/ui/Button'
import EmptyState from '@/components/feedback/EmptyState'
import PageHeader from '@/components/ui/PageHeader'
import TabSkeleton from '@/components/ui/TabSkeleton'
import GoldenSetImporter from '@/features/metrics/components/benchmark/GoldenSetImporter'
import { GOLDEN_SET_HELP } from '@/features/metrics/components/metricsConfig'
import { useBenchmarkRuns } from '@/features/metrics/hooks/useBenchmarkRuns'
import { useEvalActivityPublisher } from '@/features/activity/sources/EvalActivityProvider'
import { useEvalRuns } from '@/features/metrics/hooks/useEvalRuns'
import { isBenchmarkActive } from '../evalProfiles'
import { benchmarkReport, evaluationReport } from '../runReport'
import BenchmarkHistoryTable from './BenchmarkHistoryTable'
import RunReport from './report/RunReport'
import EvalSetupCard from './EvalSetupCard'
import RunBenchmarkCard from './RunBenchmarkCard'
import SingleEvaluation from './SingleEvaluation'

/**
 * The Eval workspace.
 *
 * A top-level destination rather than a Metrics sub-tab, because it is not
 * an aggregation over a time window: it is an operational workflow with its
 * own lifecycle. The page reads top to bottom as that workflow — which
 * dataset, which profile, what is running, what happened, what happened
 * before — with one primary action on it.
 */
export default function EvalTab() {
  const {
    datasets,
    datasetId,
    selectDataset,
    runs,
    run,
    running,
    loading,
    error,
    busy,
    startRun,
    estimateRunCost,
    importDataset,
    deleteDataset,
    refresh,
  } = useEvalRuns()

  const {
    benchmark,
    history,
    error: benchmarkError,
    busy: benchmarkBusy,
    start,
    select,
    download,
  } = useBenchmarkRuns(datasetId)

  // The page owns benchmark polling while it is mounted; the nav reads what
  // it publishes rather than polling the same run a second time.
  useEvalActivityPublisher(benchmark)

  const [importOpen, setImportOpen] = useState(false)
  const dataset = datasets.find((entry) => entry.dataset_id === datasetId)
  const benchmarkRunning = isBenchmarkActive(benchmark)

  // Both run kinds render through the same report. They are two different
  // runs, so they get one report each rather than one merged view that would
  // have to average a benchmark phase with an ad-hoc evaluation.
  const benchmarkView = useMemo(() => benchmarkReport(benchmark, dataset), [benchmark, dataset])
  const evaluationView = useMemo(() => evaluationReport(run, dataset), [run, dataset])

  const importer = (
    <GoldenSetImporter
      open={importOpen}
      onOpenChange={setImportOpen}
      onSubmit={importDataset}
      busy={busy}
      error={error}
    />
  )

  if (loading && !datasets.length) return <TabSkeleton />

  return (
    // Two elements, two jobs. The scroll viewport is the full-width outer
    // div; the max-width cap lives on the inner column. Putting both on one
    // element painted the scrollbar at the *column's* right edge — floating
    // 80px inside the window on a wide screen, with dead gutters either side
    // that swallowed the wheel.
    <div className="h-full w-full overflow-y-auto">
      {/* `[&>*]:shrink-0` is load-bearing, not decoration. Card sets
          `overflow-hidden`, and CSS only gives a flex item an automatic
          minimum size when its overflow is visible — so the cards were free
          to be crushed to a sliver (clipping their own headers and buttons)
          instead of making the column grow. */}
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 px-3 py-4 [&>*]:shrink-0 md:px-6 md:py-5">
        <PageHeader
          className="mb-2"
          title="Eval"
          description="Golden sets, benchmark profiles and quality diagnostics"
          icon={FlaskConical}
          actions={
            <Button
              variant="secondary"
              size="sm"
              onClick={refresh}
              disabled={loading}
              leftIcon={<RefreshCw size={13} className={loading ? 'animate-spin' : ''} />}
            >
              Refresh
            </Button>
          }
        />

        {!datasets.length ? (
          <>
            <EmptyState
              icon={FlaskConical}
              title="No golden set yet"
              description={
                'Live traffic can only show proxy quality. Recall and nDCG need ' +
                'ground truth, which is a set of queries somebody labelled by hand.'
              }
              action={
                <div className="flex flex-col items-center gap-4">
                  <ol
                    className="max-w-md list-decimal space-y-1 pl-5 text-left text-[13px]"
                    style={{ color: 'var(--fg-muted)' }}
                  >
                    {GOLDEN_SET_HELP.map((step) => (
                      <li key={step}>{step}</li>
                    ))}
                  </ol>
                  <Button onClick={() => setImportOpen(true)} leftIcon={<Upload size={14} />}>
                    Import a dataset
                  </Button>
                </div>
              }
            />
            {importer}
          </>
        ) : (
          <>
            {(error || benchmarkError) && (
              <div
                className="flex items-center justify-between gap-3 rounded-xl px-4 py-3 text-[15px]"
                style={{
                  background: 'var(--danger-soft)',
                  border: '1px solid rgba(239,68,68,0.25)',
                  color: 'var(--danger)',
                }}
                role="alert"
              >
                <span className="flex items-center gap-2.5">
                  <AlertTriangle size={15} aria-hidden="true" />
                  {error || benchmarkError}
                </span>
                <Button variant="secondary" size="sm" onClick={refresh}>
                  Retry
                </Button>
              </div>
            )}

            <EvalSetupCard
              datasets={datasets}
              datasetId={datasetId}
              dataset={dataset}
              busy={busy}
              running={running || benchmarkRunning}
              onSelect={selectDataset}
              onImport={() => setImportOpen(true)}
              onDelete={deleteDataset}
            />

            <RunBenchmarkCard
              itemCount={dataset?.item_count}
              ready={Boolean(datasetId)}
              busy={benchmarkBusy}
              benchmark={benchmark}
              running={benchmarkRunning}
              onStart={start}
            >
              <SingleEvaluation
                dataset={dataset}
                datasetId={datasetId}
                run={run}
                busy={busy}
                running={running}
                onStart={startRun}
                onEstimate={estimateRunCost}
              />
            </RunBenchmarkCard>

            <RunReport
              report={benchmarkView}
              history={history}
              dataset={dataset}
              busy={benchmarkBusy}
              onDownload={download}
              onRetry={() => start(benchmark?.profile)}
            />

            <RunReport
              report={evaluationView}
              runs={runs}
              dataset={dataset}
              busy={busy}
              onRetry={() => startRun(run?.mode || 'retrieval')}
            />

            <BenchmarkHistoryTable
              history={history}
              selectedId={benchmark?.benchmark_id}
              busy={benchmarkBusy}
              onSelect={select}
              onDownload={download}
            />

            {importer}
          </>
        )}
      </div>
    </div>
  )
}
