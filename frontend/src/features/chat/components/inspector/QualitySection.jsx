'use client'

import { formatAbsoluteDateTime } from '@/lib/formatting/datetime'
import { buildAnswerQuality, hasMeasuredScores, scoreColor } from '@/features/chat/utils/answerQuality'
import { ScoreBar, TechnicalValue, RedactedBlock, Empty } from './shared'
import { useI18n } from '@/i18n'

const VERDICT_COLOR = {
  pass: 'var(--success)',
  revise: 'var(--warning)',
  fail: 'var(--danger)',
}

/**
 * The judge's verdict for this turn.
 *
 * When the judge did not run, its scores arrive as zeros; showing them as
 * `0%` would read as a damning evaluation of an answer nobody evaluated, so an
 * unmeasured review states answerability instead.
 */
export default function QualitySection({ review, sources, retrievalSummary, debugPayloads = {} }) {
  const { locale, t } = useI18n()
  const safetyBlocks = [
    {
      label: t('inspector.inputSafetyFlags'),
      content: debugPayloads.input_safety_flags ?? debugPayloads.raw_input_safety_flags,
    },
    {
      label: t('inspector.outputSafetyFlags'),
      content: debugPayloads.output_safety_flags ?? debugPayloads.raw_output_safety_flags,
    },
  ].filter((block) => block.content != null && block.content !== '')

  if (!review && !safetyBlocks.length) {
    return <Empty label={t('inspector.emptyQuality')} />
  }

  const measured = hasMeasuredScores(review)
  const quality = buildAnswerQuality({ review, sources, retrievalSummary })
  const verdict = review?.verdict || null
  const createdAt = formatAbsoluteDateTime(review?.created_at, locale)

  return (
    <div className="space-y-4">
      {verdict ? (
        <div className="flex items-center justify-between rounded-lg border border-border bg-bg-tertiary px-3 py-2.5">
          <span className="text-[13px] text-text-muted">{t('inspector.verdict')}</span>
          <span
            className="rounded-full px-2.5 py-0.5 text-[13px] font-semibold capitalize"
            style={{
              backgroundColor: `${VERDICT_COLOR[verdict] || 'var(--fg-soft)'}20`,
              color: VERDICT_COLOR[verdict] || 'var(--fg-soft)',
            }}
          >
            {verdict}
          </span>
        </div>
      ) : null}

      {measured ? (
        <div className="space-y-3">
          <ScoreBar
            label={t('eval.groundedness')}
            value={review.groundedness_score}
            color={scoreColor(review.groundedness_score)}
          />
          <ScoreBar
            label={t('eval.completeness')}
            value={review.completeness_score}
            color={scoreColor(review.completeness_score)}
          />
          <ScoreBar
            label={t('eval.safety')}
            value={review.safety_score}
            color={scoreColor(review.safety_score)}
          />
        </div>
      ) : (
        <div className="rounded-lg border border-border bg-bg-tertiary px-3 py-2 text-[13px] text-text-muted">
          {quality.kind === 'unsupported'
            ? t('chat.answerabilityLine', { value: t(quality.answerabilityKey) })
            : t('inspector.judgeDidNotScore')}
        </div>
      )}

      {review?.issues?.length ? (
        <div>
          <div className="mb-1.5 text-[13px] font-medium text-text-muted">{t('inspector.issues')}</div>
          <div className="space-y-1">
            {review.issues.map((issue, index) => (
              <div
                key={`${issue}-${index}`}
                className="flex items-start gap-2 rounded-lg bg-bg-tertiary px-2.5 py-1.5 text-[13px] text-text-secondary"
              >
                <span className="mt-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warning" />
                {issue}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {(review?.model_name || createdAt || review?.review_id) ? (
        <div className="grid grid-cols-1 gap-1.5 rounded-lg border border-border px-3 py-2 text-xs text-text-muted">
          {review.model_name ? (
            <div className="flex items-center justify-between gap-2">
              <span>{t('inspector.evaluatorModel')}</span>
              <TechnicalValue title={review.model_name}>{review.model_name}</TechnicalValue>
            </div>
          ) : null}
          {createdAt ? (
            <div className="flex items-center justify-between gap-2">
              <span>{t('inspector.evaluated')}</span>
              <span className="text-text-secondary">{createdAt}</span>
            </div>
          ) : null}
          {review.review_id ? (
            <div className="flex items-center justify-between gap-2">
              <span>{t('inspector.reviewId')}</span>
              <TechnicalValue title={review.review_id}>{review.review_id}</TechnicalValue>
            </div>
          ) : null}
        </div>
      ) : null}

      {safetyBlocks.map((block) => (
        <RedactedBlock key={block.label} label={block.label} content={block.content} />
      ))}
    </div>
  )
}
