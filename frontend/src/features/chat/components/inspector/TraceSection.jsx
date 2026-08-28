'use client'

import { DataCell } from '@/components/ui/DataDisplay'
import ProgressBar from '@/components/ui/ProgressBar'
import { formatDuration } from '@/lib/formatting/datetime'
import { nodeStyle, TechnicalValue, RedactedBlock, Empty } from './shared'

/** A zero UUID is a placeholder the backend never filled in, not an identifier. */
const PLACEHOLDER_ID = /^[0-]+$/

export function usableIdentifiers(entries) {
  return entries
    .filter(([, value]) => value != null && value !== '')
    .map(([label, value]) => [label, String(value)])
    .filter(([, value]) => !PLACEHOLDER_ID.test(value))
    .map(([label, value]) => ({ label, value }))
}

/** Correlation identifiers and the per-node execution timeline. */
export default function TraceSection({ identifiers = [], traceEvents = [], debugPayloads = {} }) {
  const ids = usableIdentifiers(identifiers)
  const structuredCandidates = debugPayloads.output_safety_structured_output_candidates
    ? {
        selected_payload_index: debugPayloads.output_safety_structured_output_selected_index,
        selection_policy: debugPayloads.output_safety_structured_output_selection_policy,
        extraction_mode: debugPayloads.output_safety_structured_output_extraction_mode,
        candidates: debugPayloads.output_safety_structured_output_candidates,
        raw_output: debugPayloads.output_safety_raw_output,
      }
    : null

  if (!ids.length && !traceEvents.length && !structuredCandidates) {
    return <Empty label="No trace data for this turn" />
  }

  const totalLatency = traceEvents.reduce(
    (total, event) => total + (Number.isFinite(event.latency) ? event.latency : 0),
    0
  )
  const maxLatency = Math.max(...traceEvents.map((event) => event.latency || 0), 1)

  return (
    <div className="space-y-3">
      {ids.length ? (
        <div className="grid grid-cols-2 gap-x-3 gap-y-2 rounded-lg border border-border px-3 py-2.5">
          {ids.map(({ label, value }) => (
            <div key={label} className="min-w-0">
              <div className="text-xs uppercase tracking-wide text-text-muted">{label}</div>
              <TechnicalValue title={value}>{value}</TechnicalValue>
            </div>
          ))}
        </div>
      ) : null}

      {traceEvents.length ? (
        <>
          <DataCell reverse center mono label="Total latency" value={formatDuration(totalLatency) || '—'} />
          <div className="space-y-1.5">
            {traceEvents.map((trace, index) => {
              const { color, label } = nodeStyle(trace.node)
              const percent = Math.max(4, Math.round(((trace.latency || 0) / maxLatency) * 100))
              const counters = trace.counters && Object.keys(trace.counters).length > 0
                ? Object.entries(trace.counters)
                : null

              return (
                <div key={`${trace.node}-${index}`} className="rounded-lg border border-border bg-bg-tertiary p-2.5">
                  <div className="mb-1.5 flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: color }} />
                      <span className="truncate text-[13px] font-medium text-text-primary">{label}</span>
                      {trace.decision && trace.decision !== 'completed' && trace.decision !== trace.node ? (
                        <span className="shrink-0 rounded-full bg-bg-elevated px-1.5 py-0.5 text-xs text-text-muted">
                          Decision: {trace.decision}
                        </span>
                      ) : null}
                    </div>
                    <span dir="ltr" className="shrink-0 font-mono text-xs text-text-muted">
                      {formatDuration(trace.latency) || '—'}
                    </span>
                  </div>

                  <ProgressBar
                    value={percent}
                    color={color}
                    thickness="xs"
                    track="bg-bg-elevated"
                    fillOpacity={0.7}
                    className="mb-1"
                  />

                  {counters ? (
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 pt-0.5">
                      {counters.map(([key, value]) => (
                        <span key={key} className="text-xs text-text-muted">
                          <span className="text-text-secondary">{value}</span> {key.replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              )
            })}
          </div>
        </>
      ) : null}

      {structuredCandidates ? (
        <RedactedBlock label="Structured output candidates" content={structuredCandidates} />
      ) : null}
    </div>
  )
}
