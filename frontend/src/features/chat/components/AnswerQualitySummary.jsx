'use client'

/**
 * The compact quality state that sits under every answer by default.
 *
 * It carries no identifiers, no model slugs and no raw evaluator payload —
 * those live in the Developer Inspector. A turn with nothing behind it states
 * its answerability in words rather than as a row of zero percentages, and
 * stops there: no decision is claimed that the backend did not report.
 */

const TONE_COLOR = {
  success: 'var(--success)',
  warning: 'var(--warning)',
  error: 'var(--danger)',
  neutral: 'var(--fg-soft)',
}

export default function AnswerQualitySummary({ quality }) {
  if (!quality) return null

  if (quality.kind === 'unsupported') {
    return (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--fg-soft)]">
        <span>
          Answerability: <span className="font-medium text-[var(--fg-muted)]">{quality.answerability}</span>
        </span>
      </div>
    )
  }

  if (!quality.parts.length) return null

  return (
    <div className="flex items-center gap-1.5 text-xs text-[var(--fg-soft)]">
      <span
        className="h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ background: TONE_COLOR[quality.tone] || TONE_COLOR.neutral }}
        aria-hidden="true"
      />
      <span>{quality.parts.join(' · ')}</span>
    </div>
  )
}
