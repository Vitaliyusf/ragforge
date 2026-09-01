import { describe, expect, it } from 'vitest'
import {
  buildAnswerQuality,
  formatScore,
  hasMeasuredScores,
  toPercent,
} from './answerQuality'
import { translate } from '@/i18n/translate'

describe('answer quality', () => {
  it('summarises a grounded, reviewed answer compactly', () => {
    const quality = buildAnswerQuality({
      review: {
        verdict: 'pass',
        groundedness_score: 0.91,
        completeness_score: 0.84,
        safety_score: 0.98,
      },
      sources: [{ source_name: 'a.pdf' }, { source_name: 'b.pdf' }, { source_name: 'c.pdf' }],
    })

    expect(quality.kind).toBe('summary')
    expect(quality.parts.join(' · ')).toBe('Grounded · Sources: 3 · Review passed')
    expect(quality.tone).toBe('success')
  })

  it('counts a user-facing source as a document, not as a chunk', () => {
    const quality = buildAnswerQuality({
      review: { verdict: 'pass', groundedness_score: 0.8 },
      sources: [
        { source_name: 'Handbook.pdf', page: 1 },
        { source_name: 'Handbook.pdf', page: 2 },
        { source_name: 'Notes.md' },
      ],
      retrievalSummary: { chunk_count: 3 },
    })

    // Three chunks from two documents: the reader is told two sources, and the
    // chunk count is carried separately for the Developer Inspector. The count
    // is labelled rather than pluralised so the same phrasing works in Hebrew.
    expect(quality.parts).toContain('Sources: 2')
    expect(quality.sourceCount).toBe(2)
    expect(quality.chunkCount).toBe(3)
  })

  it('states answerability without claiming a decision when nothing was retrieved', () => {
    const quality = buildAnswerQuality({
      // The shape a skipped judge produces: floats coerced to zero.
      review: { groundedness_score: 0, completeness_score: 0, safety_score: 0 },
      sources: [],
    })

    expect(quality.kind).toBe('unsupported')
    expect(quality.answerability).toBe('No supporting evidence')
    // No backend field reports an abstention decision, so none is inferred.
    expect(quality.decision).toBeUndefined()
    expect(JSON.stringify(quality)).not.toMatch(/abstain/i)
  })

  it('does not read as unsupported when passages were retrieved', () => {
    const quality = buildAnswerQuality({
      review: { groundedness_score: 0, completeness_score: 0, safety_score: 0 },
      sources: [{ source_name: 'a.pdf' }, { source_name: 'b.pdf' }],
    })

    expect(quality.kind).toBe('summary')
    expect(quality.parts).toEqual(['Sources: 2'])
  })

  it('flags a failed review', () => {
    const quality = buildAnswerQuality({
      review: { verdict: 'fail', groundedness_score: 0.2 },
      sources: [{ source_name: 'a.pdf' }],
    })

    expect(quality.tone).toBe('error')
    expect(quality.parts).toContain('Review failed')
  })

  it('treats an all-zero review as unmeasured', () => {
    expect(hasMeasuredScores({ groundedness_score: 0, completeness_score: 0, safety_score: 0 })).toBe(false)
    expect(hasMeasuredScores({ groundedness_score: 0.4 })).toBe(true)
    expect(hasMeasuredScores(null)).toBe(false)
  })

  it('carries the same summary as translation keys, so Hebrew reads natively', () => {
    const quality = buildAnswerQuality({
      review: { verdict: 'pass', groundedness_score: 0.91 },
      sources: [{ source_name: 'a.pdf' }, { source_name: 'b.pdf' }],
    })

    const hebrew = quality.partKeys.map((part) => translate('he', part.key, part.vars))
    expect(hebrew).toEqual(['מבוססת על המקורות', 'מקורות: 2', 'בדיקת האיכות עברה'])
  })

  it('states answerability in Hebrew from the same descriptor', () => {
    const quality = buildAnswerQuality({ review: null, sources: [] })
    expect(quality.answerabilityKey).toBe('chat.noSupportingEvidence')
    expect(translate('he', quality.answerabilityKey)).toBe('לא נמצאו מקורות תומכים')
  })

  it('never renders an unmeasured score as a number', () => {
    expect(toPercent(undefined)).toBeNull()
    expect(formatScore(undefined)).toBe('—')
    expect(formatScore(0.917)).toBe('92%')
  })
})
