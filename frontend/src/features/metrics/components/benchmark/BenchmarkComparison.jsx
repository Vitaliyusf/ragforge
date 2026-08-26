const GROUPS = {
  dataset: ['dataset_id', 'dataset_version', 'dataset_sha256'],
  config: ['manifest.dataset.phases', 'manifest.chunking', 'manifest.vector_store'],
  model: ['manifest.embedding', 'manifest.llm'],
  retrieval: ['manifest.retrieval'],
}

function atPath(value, path) {
  return path.split('.').reduce((current, key) => current?.[key], value)
}

function same(left, right) {
  return left != null && right != null && JSON.stringify(left) === JSON.stringify(right)
}

export function compatibility(baseline, candidate) {
  const warnings = []
  Object.entries(GROUPS).forEach(([category, paths]) => paths.forEach((field) => {
    const left = atPath(baseline, field)
    const right = atPath(candidate, field)
    if (!same(left, right)) warnings.push({ category, field, kind: left == null || right == null ? 'unknown' : 'mismatch' })
  }))
  return { compatible: warnings.length === 0, warnings }
}

function priorRuns(candidate, history) {
  const candidateTime = Date.parse(candidate?.created_at || '')
  return history.filter((run) => run.benchmark_id !== candidate?.benchmark_id &&
    ['completed', 'partial', 'failed', 'interrupted'].includes(run.status) &&
    (!Number.isFinite(candidateTime) || !Number.isFinite(Date.parse(run.created_at || '')) || Date.parse(run.created_at) < candidateTime))
}

export function selectBaseline(candidate, history = []) {
  return priorRuns(candidate, history).find((run) => compatibility(run, candidate).compatible) || null
}

function rows(baseline, candidate) {
  const baselinePhases = Object.fromEntries((baseline.phases || []).map((phase) => [phase.name, phase]))
  return (candidate.phases || []).flatMap((phase) => {
    const previous = baselinePhases[phase.name]
    if (!previous) return []
    return [
      { name: `${phase.name} MRR`, baseline: previous.results?.mrr, candidate: phase.results?.mrr },
      { name: `${phase.name} latency`, baseline: previous.results?.mean_latency_ms, candidate: phase.results?.mean_latency_ms, suffix: ' ms' },
    ].filter((row) => Number.isFinite(row.baseline) || Number.isFinite(row.candidate))
  })
}

function deltas(baseline, candidate) {
  if (!Number.isFinite(baseline) || !Number.isFinite(candidate)) return { absolute: null, percentage: null }
  const absolute = candidate - baseline
  return { absolute, percentage: baseline === 0 ? null : (absolute / Math.abs(baseline)) * 100 }
}

export default function BenchmarkComparison({ candidate, history = [] }) {
  if (!candidate || !['completed', 'partial', 'failed', 'interrupted'].includes(candidate.status)) return null
  const previous = priorRuns(candidate, history)
  const baseline = selectBaseline(candidate, history)
  if (!baseline) {
    const warnings = previous[0] ? compatibility(previous[0], candidate).warnings : []
    const categories = [...new Set(warnings.map((warning) => warning.category))]
    return <section className="mt-4 rounded border p-3 text-[13px]" style={{ borderColor: 'var(--border)' }} aria-label="Benchmark comparison">
      <h3 className="font-medium">Benchmark comparison</h3>
      <p className="mt-1" style={{ color: 'var(--warning, #b7791f)' }}>
        {previous.length === 0 ? 'No previous benchmark is available as a baseline.' : `No compatible baseline. Check ${categories.join(', ') || 'recorded provenance'} compatibility.`}
      </p>
    </section>
  }
  return <section className="mt-4 rounded border p-3 text-[13px]" style={{ borderColor: 'var(--border)' }} aria-label="Benchmark comparison">
    <h3 className="font-medium">Benchmark comparison</h3>
    <p className="mt-1 text-xs" style={{ color: 'var(--fg-muted)' }}>Baseline {baseline.benchmark_id} → Candidate {candidate.benchmark_id}</p>
    <div className="mt-2 overflow-x-auto"><table className="w-full text-left">
      <thead><tr><th>Metric</th><th>Baseline</th><th>Candidate</th><th>Δ</th><th>Δ%</th></tr></thead>
      <tbody>{rows(baseline, candidate).map((row) => {
        const delta = deltas(row.baseline, row.candidate)
        return <tr key={row.name}><td>{row.name}</td><td>{format(row.baseline, row.suffix)}</td><td>{format(row.candidate, row.suffix)}</td><td>{formatSigned(delta.absolute, row.suffix)}</td><td>{formatSigned(delta.percentage, '%')}</td></tr>
      })}</tbody>
    </table></div>
  </section>
}

function format(value, suffix = '') { return Number.isFinite(value) ? `${value.toFixed(3)}${suffix || ''}` : '—' }
function formatSigned(value, suffix = '') { return Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${value.toFixed(2)}${suffix}` : '—' }
