'use client'

const PIPELINE_STAGES = [
  { key: 'extraction', label: 'Extract' },
  { key: 'review', label: 'Review' },
  { key: 'chunking', label: 'Chunk' },
  { key: 'summary', label: 'Summary' },
  { key: 'embedding', label: 'Embed' },
  { key: 'semantic', label: 'Semantic' },
  { key: 'vector', label: 'Vector' },
  { key: 'metadata', label: 'Metadata' },
]

const STAGE_DONE_VALUES = new Set(['done', 'complete', 'completed', 'ready', 'skipped', 'not_required'])
const STAGE_RUNNING_VALUES = new Set(['running', 'processing'])

function normalizeStageValue(value) {
  const normalized = String(value ?? 'waiting').toLowerCase()
  if (STAGE_DONE_VALUES.has(normalized)) return 'done'
  if (STAGE_RUNNING_VALUES.has(normalized)) return 'running'
  if (normalized === 'error') return 'error'
  return 'waiting'
}

// Each state carries a texture as well as a colour — solid, pulsing, striped,
// or hollow — so the pipeline stays readable without colour perception.
const STAGE_SEGMENT_STYLES = {
  done: { className: 'bg-success' },
  running: { className: 'bg-warning animate-pulse' },
  error: {
    className: 'bg-danger',
    style: {
      backgroundImage:
        'repeating-linear-gradient(45deg, transparent 0 2px, rgba(255,255,255,0.55) 2px 4px)',
    },
  },
  waiting: { className: 'bg-bg-tertiary border border-border' },
}

function PipelineBar({ stage }) {
  if (!stage || typeof stage !== 'object') return null

  const stages = PIPELINE_STAGES.map(({ key, label }) => ({
    key,
    label,
    value: stage[key] ?? 'waiting',
    state: normalizeStageValue(stage[key]),
  }))

  const doneCount = stages.filter((entry) => entry.state === 'done').length
  const running = stages.find((entry) => entry.state === 'running')
  const failed = stages.filter((entry) => entry.state === 'error')

  // Read out in place of the eight individual segments, which carry no text.
  const summary = [
    `Pipeline: ${doneCount} of ${stages.length} stages complete`,
    running ? `${running.label.toLowerCase()} running` : null,
    failed.length ? `${failed.map((entry) => entry.label.toLowerCase()).join(', ')} failed` : null,
  ]
    .filter(Boolean)
    .join(', ')

  return (
    <div className="mt-3">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="text-xs font-medium text-text-secondary">Pipeline</span>
        <span className="text-xs tabular-nums text-text-secondary">
          {doneCount}/{stages.length}
        </span>
      </div>
      <div className="flex gap-1" role="img" aria-label={summary}>
        {stages.map(({ key, label, value, state }) => {
          const segment = STAGE_SEGMENT_STYLES[state]
          return (
            <div key={key} className="group relative flex-1">
              <div className={`h-2 rounded-full ${segment.className}`} style={segment.style} />
              <div className="pointer-events-none absolute bottom-3.5 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-lg border border-border bg-bg-elevated px-2 py-1 text-xs font-medium text-text-secondary opacity-0 shadow-lg transition-opacity group-hover:opacity-100">
                {label}: <span className="capitalize text-text-primary">{value}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default PipelineBar
