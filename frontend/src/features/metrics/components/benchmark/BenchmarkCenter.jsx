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
  const { benchmark, error, busy, start, download } = useBenchmarkRuns(datasetId)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const phases = benchmark?.phases || []
  const progress = benchmark?.progress || {}
  const running = benchmark && !TERMINAL_EXPORTABLE.has(benchmark.status)
  const measured = phases.filter((phase) => ['completed', 'partial'].includes(phase.status))

  return (
    <Card>
      <CardHeader title="Benchmark center" description="Prepare a golden set, then run the diagnostic phases in their safe order." action={
        <div className="flex gap-2">
          <Button size="sm" onClick={() => setConfirmOpen(true)} disabled={!ready || busy || running} leftIcon={<Play size={13} />}>
            {running ? 'Benchmark running…' : 'Run full benchmark'}
          </Button>
          <Button variant="secondary" size="sm" onClick={download} disabled={!TERMINAL_EXPORTABLE.has(benchmark?.status) || busy} leftIcon={<Download size={13} />}>
            Download ZIP
          </Button>
        </div>
      } />
      <p className="text-[13px]" style={{ color: 'var(--fg-muted)' }}>
        {ready ? `${datasetName || 'Selected golden set'} is ready for a full diagnostic run.` : 'Import and validate a golden set before starting a benchmark.'}
      </p>
      {benchmark && <>
        <div className="mt-3 flex items-center gap-2 text-[13px]"><Badge dot>{benchmark.status}</Badge><span>{progress.completed_phases ?? 0} completed, {progress.partial_phases ?? 0} partial of {progress.executable_phases ?? progress.total_phases ?? phases.length} executable phases</span></div>
        <ul className="mt-3 space-y-1 text-[13px]">
          {phases.map((phase) => <li key={phase.name} className="flex justify-between gap-4"><span>{PHASE_LABELS[phase.name] || phase.name}</span><span style={{ color: 'var(--fg-muted)' }}>{phase.status}{phase.reason || phase.error ? ` — ${phase.reason || phase.error}` : ''}</span></li>)}
        </ul>
        {measured.length > 0 && <div className="mt-3 text-[13px]" style={{ color: 'var(--fg-muted)'}}>
          <p className="font-medium" style={{ color: 'var(--fg)' }}>Summary</p>
          {measured.map((phase) => <p key={phase.name}>{PHASE_LABELS[phase.name] || phase.name}: MRR {formatMetric(phase.results?.mrr)}, mean latency {formatMetric(phase.results?.mean_latency_ms, ' ms')}</p>)}
        </div>}
        {benchmark.error && <p className="mt-3 text-[13px]" style={{ color: 'var(--danger)' }}>{benchmark.error}</p>}
      </>}
      {error && <p className="mt-3 text-[13px]" style={{ color: 'var(--danger)' }}>{error}</p>}
      <ConfirmModal open={confirmOpen} onOpenChange={setConfirmOpen} title="Run the full benchmark?" description="This runs the retrieval check first. End-to-end phases may call the configured model after the free check succeeds." confirmLabel="Start benchmark" onConfirm={() => { setConfirmOpen(false); start() }} />
    </Card>
  )
}

function formatMetric(value, suffix = '') {
  return Number.isFinite(value) ? `${value.toFixed(value <= 1 ? 3 : 0)}${suffix}` : '—'
}
