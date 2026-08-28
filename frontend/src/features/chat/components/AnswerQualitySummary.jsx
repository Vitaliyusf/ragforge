'use client'

/**
 * The compact quality state that sits under every answer by default.
 *
 * It carries no identifiers, no model slugs and no raw evaluator payload —
 * those live in the Developer Inspector. An abstention is stated in words
 * rather than as a row of zero percentages.
 */

const TONE_COLOR = {
  success: 'var(--success)',
  warning: 'var(--warning)',
  error: 'var(--danger)',
  neutral: 'var(--fg-soft)',
}

export default function AnswerQualitySummary({ quality }) {
  if (!quality) return null

  if (quality.kind === 'abstention') {
    return (
      <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--fg-soft)]">
        <span>
          Answerability: <span className="font-medium text-[var(--fg-muted)]">{quality.answerability}</span>
        </span>
        <span>
          Decision: <span className="font-medium text-[var(--fg-muted)]">{quality.decision}</span>
        </span>
      </div>
    )
  }

  if (!quality.parts.length) return null

  return (
    <div className="mt-1.5 flex items-center gap-1.5 text-xs text-[var(--fg-soft)]">
      <span
        className="h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ background: TONE_COLOR[quality.tone] || TONE_COLOR.neutral }}
        aria-hidden="true"
      />
      <span>{quality.parts.join(' · ')}</span>
    </div>
  )
}
