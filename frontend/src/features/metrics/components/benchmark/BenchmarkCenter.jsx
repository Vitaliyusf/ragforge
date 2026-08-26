'use client'

import { useState } from 'react'
import { Download, Play } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import Card, { CardHeader } from '@/components/ui/Card'
import { ConfirmModal } from '@/components/ui/Modal'
import { useBenchmarkRuns } from '../../hooks/useBenchmarkRuns'

const PHASE_LABELS = {
  retrieval_base: 'Retrieval baseline', retrieval_extended: 'Extended retrieval',
  end_to_end_regular: 'End-to-end', end_to_end_extended: 'Extended end-to-end',
}
const TERMINAL_EXPORTABLE = new Set(['completed', 'partial', 'failed', 'interrupted'])

export default function BenchmarkCenter({ datasetId, datasetName, ready }) {
  const { benchmark, history, error, busy, start, select, download } = useBenchmarkRuns(datasetId)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const phases = benchmark?.phases || []
  const progress = benchmark?.progress || {}
  const running = benchmark && !TERMINAL_EXPORTABLE.has(benchmark.status)
  const measured = phases.filter((phase) => ['completed', 'partial'].includes(phase.status))
  const executableTotal = progress.executable_phases ?? progress.total_phases ?? phases.filter((phase) => phase.status !== 'unsupported').length
  const completedPhases = progress.completed_phases ?? 0
  const activePhase = phases.find((phase) => phase.status === 'running')
  const itemProgress = activePhase?.item_progress || {}
  // The per-phase counters carry outcomes only; every executable phase scores
  // the whole dataset, so its denominator is the benchmark's items-per-phase.
  const itemsPerPhase = progress.items_per_phase ?? 0

  return (
    <Card>
      <CardHeader title="Benchmark center" description="Prepare a golden set, then run the diagnostic phases in their safe order." action={
        <div className="flex gap-2">
          <Button size="sm" onClick={() => setConfirmOpen(true)} disabled={!ready || busy || running} leftIcon={<Play size={13} />}>
            {running ? 'Benchmark running…' : 'Run full benchmark'}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => download()} disabled={!TERMINAL_EXPORTABLE.has(benchmark?.status) || busy} leftIcon={<Download size={13} />}>
            Download Diagnostic ZIP
          </Button>
        </div>
      } />
      <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
        {ready ? `Golden Set / Dataset: ${datasetName || 'Selected golden set'} is ready for a Benchmark Run.` : 'Import and validate a Golden Set / Dataset before starting a Benchmark Run.'}
      </p>
      {benchmark && <>
        <div className="mt-3 flex items-center gap-2 text-[13px]"><Badge dot>{benchmark.status}</Badge><span>Benchmark Run: {completedPhases} / {executableTotal} executable phases complete</span></div>
        {running && <p className="mt-2 text-[13px]" style={{ color: 'var(--fg-muted)' }}>Safe to leave this page. The benchmark runs on the server and progress is saved automatically.</p>}
        <ul className="mt-3 space-y-1 text-[13px]">
          {phases.map((phase) => <li key={phase.name} className="flex justify-between gap-4"><span>{PHASE_LABELS[phase.name] || phase.name}</span><span style={{ color: 'var(--fg-muted)' }}>{phase.status}{phase.reason || phase.error ? ` — ${phase.reason || phase.error}` : ''}</span></li>)}
        </ul>
        {activePhase && <PhaseProgress phase={activePhase} progress={itemProgress} total={itemsPerPhase} />}
        {measured.length > 0 && <div className="mt-3 text-[13px]" style={{ color: 'var(--fg-muted)'}}>
          <p className="font-medium" style={{ color: 'var(--fg)' }}>Summary</p>
          {measured.map((phase) => <p key={phase.name}>{PHASE_LABELS[phase.name] || phase.name}: MRR {formatMetric(phase.results?.mrr)}, mean latency {formatMetric(phase.results?.mean_latency_ms, ' ms')}</p>)}
        </div>}
        {benchmark.error && <p className="mt-3 text-[13px]" style={{ color: 'var(--danger)' }}>{benchmark.error}</p>}
      </>}
      <BenchmarkHistory history={history} selectedId={benchmark?.benchmark_id} busy={busy} onSelect={select} onDownload={download} />
      {error && <p className="mt-3 text-[13px]" style={{ color: 'var(--danger)' }}>{error}</p>}
      <ConfirmModal open={confirmOpen} onOpenChange={setConfirmOpen} title="Run the full benchmark?" description="This runs the retrieval check first. End-to-end phases may call the configured model after the free check succeeds." confirmLabel="Start benchmark" onConfirm={() => { setConfirmOpen(false); start() }} />
    </Card>
  )
}

function BenchmarkHistory({ history = [], selectedId, busy, onSelect, onDownload }) {
  return <section className="mt-5 border-t pt-4" style={{ borderColor: 'var(--border)' }}>
    <h3 className="text-sm font-medium">Benchmark history</h3>
    {history.length === 0 && <p className="mt-2 text-[13px]" style={{ color: 'var(--fg-muted)' }}>No benchmark runs yet. Start a benchmark to build its server-backed history.</p>}
    {history.length > 0 && <ul className="mt-2 space-y-2">
      {history.map((run) => {
        const terminal = TERMINAL_EXPORTABLE.has(run.status)
        const current = run.benchmark_id === selectedId
        const phase = run.phases?.find((item) => item.status === 'running')
        return <li key={run.benchmark_id} className="flex min-w-0 items-center gap-2 rounded border p-2 text-[13px]" style={{ borderColor: 'var(--border)' }}>
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 items-center gap-2"><span className="truncate font-medium">{run.dataset_name || run.dataset?.name || 'Golden Set'}</span><Badge dot>{run.status}</Badge></div>
            <p className="truncate text-xs" style={{ color: 'var(--fg-muted)' }}>{formatTimestamp(run.created_at || run.started_at || run.finished_at)} · {run.dataset_version ? `v${run.dataset_version} · ` : ''}{run.benchmark_id}</p>
            {phase && <p className="truncate text-xs" style={{ color: 'var(--fg-muted)' }}>Current phase: {PHASE_LABELS[phase.name] || phase.name}</p>}
          </div>
          <Button variant={current ? 'secondary' : 'ghost'} size="sm" disabled={busy || current} onClick={() => onSelect(run.benchmark_id)}>View</Button>
          {terminal && <Button variant="secondary" size="sm" disabled={busy} onClick={() => onDownload(run.benchmark_id)}>Download ZIP</Button>}
        </li>
      })}
    </ul>}
  </section>
}

function PhaseProgress({ phase, progress, total: itemsPerPhase }) {
  const total = Number(itemsPerPhase ?? 0)
  const completed = Number(progress.items_completed ?? 0)
  const percent = total ? Math.round((completed / total) * 100) : null
  const elapsed = formatElapsed(progress.phase_started_at)
  const staleSeconds = ageSeconds(progress.last_progress_at)
  return <div className="mt-3 rounded border p-3 text-[13px]" style={{ borderColor: 'var(--border)' }}>
    <p className="font-medium">{PHASE_LABELS[phase.name] || phase.name}</p>
    <p className="mt-1">{completed} / {total}{percent !== null ? `   ${percent}%` : ''}</p>
    <div className="mt-2 grid grid-cols-2 gap-y-1" style={{ color: 'var(--fg-muted)' }}>
      <span>Processed</span><span>{completed}</span><span>Successful</span><span>{progress.items_succeeded ?? 0}</span><span>Guardrail blocked</span><span>{progress.items_guardrail_blocked ?? 0}</span><span>Failed</span><span>{progress.items_failed ?? 0}</span><span>In flight</span><span>{progress.items_in_flight ?? 0}</span>
      {elapsed && <><span className="mt-2">Elapsed</span><span className="mt-2">{elapsed}</span></>}
      {staleSeconds !== null && <><span>Last progress</span><span>{formatAge(staleSeconds)} ago</span></>}
    </div>
    {staleSeconds !== null && staleSeconds >= 120 && <p className="mt-2" style={{ color: 'var(--warning, #b7791f)' }}>Possible stall: no benchmark item has completed for {formatAge(staleSeconds)}.</p>}
  </div>
}

function ageSeconds(value) {
  const timestamp = Date.parse(value || '')
  return Number.isFinite(timestamp) ? Math.max(0, Math.floor((Date.now() - timestamp) / 1000)) : null
}

function formatTimestamp(value) {
  const timestamp = Date.parse(value || '')
  return Number.isFinite(timestamp) ? new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(timestamp) : 'Unknown time'
}

function formatElapsed(value) { const seconds = ageSeconds(value); return seconds === null ? null : formatAge(seconds) }
function formatAge(seconds) { return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s` }

function formatMetric(value, suffix = '') {
  return Number.isFinite(value) ? `${value.toFixed(value <= 1 ? 3 : 0)}${suffix}` : '—'
}
