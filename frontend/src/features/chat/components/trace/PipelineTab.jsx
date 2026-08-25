'use client'

import { DataCell } from '@/components/ui/DataDisplay'
import ProgressBar from '@/components/ui/ProgressBar'
import { nodeStyle, Empty } from './shared'

function PipelineTab({ traceEvents, retrievalSummary }) {
  if (!traceEvents.length) {
    return <Empty label="No pipeline data for this turn" />
  }

  const totalLatency = traceEvents.reduce((sum, t) => sum + (t.latency || 0), 0)
  const maxLatency   = Math.max(...traceEvents.map((t) => t.latency || 0), 1)

  return (
    <div className="space-y-3">
      {retrievalSummary ? (
        <div className="grid grid-cols-2 gap-2">
          <DataCell reverse center mono label="Chunks used" value={retrievalSummary.chunk_count ?? '—'} />
          <DataCell reverse center mono label="Total latency" value={`${Math.round(totalLatency)} ms`} />
        </div>
      ) : (
        <DataCell reverse center mono label="Total latency" value={`${Math.round(totalLatency)} ms`} />
      )}

      <div className="space-y-1.5">
        {traceEvents.map((trace, index) => {
          const { color, label } = nodeStyle(trace.node)
          const pct = Math.max(4, Math.round(((trace.latency || 0) / maxLatency) * 100))
          const counters = trace.counters && Object.keys(trace.counters).length > 0
            ? Object.entries(trace.counters)
            : null

          return (
            <div key={`${trace.node}-${index}`} className="rounded-lg border border-border bg-bg-tertiary p-2.5">
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <span className="truncate text-[13px] font-medium text-text-primary">{label}</span>
                  {trace.decision && trace.decision !== 'completed' && trace.decision !== trace.node ? (
                    <span className="shrink-0 rounded-full bg-bg-elevated px-1.5 py-0.5 text-xs text-text-muted">
                      Decision: {trace.decision}
                    </span>
                  ) : null}
                </div>
                <span className="shrink-0 font-mono text-xs text-text-muted">
                  {trace.latency != null ? `${trace.latency} ms` : '—'}
                </span>
              </div>

              <ProgressBar
                value={pct}
                color={color}
                thickness="xs"
                track="bg-bg-elevated"
                fillOpacity={0.7}
                className="mb-1"
              />

              {counters ? (
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 pt-0.5">
                  {counters.map(([k, v]) => (
                    <span key={k} className="text-xs text-text-muted">
                      <span className="text-text-secondary">{v}</span> {k.replace(/_/g, ' ')}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default PipelineTab
