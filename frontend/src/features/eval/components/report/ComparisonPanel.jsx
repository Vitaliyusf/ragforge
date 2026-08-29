'use client'

import { AlertTriangle } from 'lucide-react'
import { Callout, Cell, Note, Num, ReportTable, Row } from './primitives'

/**
 * This run against the one before it.
 *
 * The comparability verdict is rendered above the deltas, never under them:
 * a delta between two runs that scored different corpora, or ran on a
 * different embedding model, is not a regression or an improvement but a
 * category error. When the provenance disagrees the report says so first,
 * lists exactly which fields moved, and leaves every delta uncoloured —
 * green on a number nobody can compare is a claim the evidence does not
 * support.
 */
export default function ComparisonPanel({ comparison }) {
  if (!comparison) return null

  if (!comparison.baseline) {
    return <Note>No earlier run is available to compare this one against.</Note>
  }

  return (
    <div className="flex flex-col gap-3">
      {!comparison.comparable && (
        <Callout tone="warning" icon={AlertTriangle} title="Not directly comparable">
          <p>
            This run and the baseline disagree on provenance, so the differences below are not
            evidence of a regression or an improvement. Re-run both under the same configuration
            before reading them as a change in quality.
          </p>
        </Callout>
      )}

      <p className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
        Baseline {comparison.baseline.benchmark_id} → this run.
      </p>

      {comparison.changes.length > 0 && (
        <ReportTable
          caption="Configuration fields that differ between the two runs"
          columns={[
            { key: 'field', label: 'Changed field' },
            { key: 'baseline', label: 'Baseline' },
            { key: 'candidate', label: 'This run' },
          ]}
        >
          {comparison.changes.map((change) => (
            <Row key={change.field}>
              <th
                scope="row"
                className="py-1.5 pr-3 text-left font-normal"
                style={{ color: 'var(--fg)' }}
              >
                {change.label}
                {change.kind === 'unknown' && (
                  <span className="block text-[12px]" style={{ color: 'var(--fg-soft)' }}>
                    One of the two runs did not record this.
                  </span>
                )}
              </th>
              <Cell className="break-all">{change.baselineText}</Cell>
              <Cell className="break-all" color="var(--warning)">
                {change.candidateText}
              </Cell>
            </Row>
          ))}
        </ReportTable>
      )}

      {comparison.rows.length === 0 ? (
        <Note>The two runs share no phase that both measured.</Note>
      ) : (
        <ReportTable
          caption="Metric deltas against the baseline run"
          columns={[
            { key: 'metric', label: 'Metric' },
            { key: 'baseline', label: 'Baseline', align: 'right' },
            { key: 'candidate', label: 'This run', align: 'right' },
            { key: 'delta', label: 'Δ', align: 'right' },
            { key: 'percent', label: 'Δ%', align: 'right' },
          ]}
        >
          {comparison.rows.map((row) => (
            <Row key={row.key}>
              <th
                scope="row"
                className="py-1.5 pr-3 text-left font-normal"
                style={{ color: 'var(--fg)' }}
              >
                {row.label}
              </th>
              <Num>{row.baselineText}</Num>
              <Num>{row.candidateText}</Num>
              <Num color={toneColor(row.tone)}>{row.deltaText}</Num>
              <Num color={toneColor(row.tone)}>{row.deltaPercentText}</Num>
            </Row>
          ))}
        </ReportTable>
      )}
    </div>
  )
}

/** No colour unless the metric has a defined direction and the runs compare. */
function toneColor(tone) {
  if (tone === 'success') return 'var(--success)'
  if (tone === 'danger') return 'var(--danger)'
  return 'var(--fg-muted)'
}
