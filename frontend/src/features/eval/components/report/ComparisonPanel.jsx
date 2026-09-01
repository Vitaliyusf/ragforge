'use client'

import { AlertTriangle } from 'lucide-react'
import { Callout, Cell, Note, Num, ReportTable, Row } from './primitives'
import { useI18n } from '@/i18n'

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
  const { t } = useI18n()
  if (!comparison) return null

  if (!comparison.baseline) {
    return <Note>{t('evalReport.noBaseline')}</Note>
  }

  return (
    <div className="flex flex-col gap-3">
      {!comparison.comparable && (
        <Callout tone="warning" icon={AlertTriangle} title={t('evalReport.notComparable')}>
          <p>{t('evalReport.notComparableBody')}</p>
        </Callout>
      )}

      <p className="text-[12px]" style={{ color: 'var(--fg-soft)' }}>
        {t('evalReport.baselineArrow', { id: comparison.baseline.benchmark_id })}
      </p>

      {comparison.changes.length > 0 && (
        <ReportTable
          caption={t('evalReport.changedFieldsCaption')}
          columns={[
            { key: 'field', label: t('evalReport.changedField') },
            { key: 'baseline', label: t('evalReport.baseline') },
            { key: 'candidate', label: t('evalReport.thisRun') },
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
                    {t('evalReport.oneRunDidNotRecord')}
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
        <Note>{t('evalReport.noSharedPhase')}</Note>
      ) : (
        <ReportTable
          caption={t('evalReport.deltasCaption')}
          columns={[
            { key: 'metric', label: t('evalReport.metric') },
            { key: 'baseline', label: t('evalReport.baseline'), align: 'right' },
            { key: 'candidate', label: t('evalReport.thisRun'), align: 'right' },
            // Δ and Δ% are mathematical notation, not copy.
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
