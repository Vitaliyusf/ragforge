import { describe, expect, it } from 'vitest'
import {
  buildAnswerQuality,
  formatScore,
  hasMeasuredScores,
  toPercent,
} from './answerQuality'

describe('answer quality', () => {
  it('summarises a grounded, reviewed answer compactly', () => {
    const quality = buildAnswerQuality({
      review: {
        verdict: 'pass',
        groundedness_score: 0.91,
        completeness_score: 0.84,
        safety_score: 0.98,
      },
      sources: [{}, {}, {}],
    })

    expect(quality.kind).toBe('summary')
    expect(quality.parts.join(' · ')).toBe('Grounded · 3 sources · Review passed')
    expect(quality.tone).toBe('success')
  })

  it('prefers the server chunk count over the source array length', () => {
    const quality = buildAnswerQuality({
      review: { verdict: 'pass', groundedness_score: 0.8 },
      sources: [{}],
      retrievalSummary: { chunk_count: 5 },
    })

    expect(quality.parts).toContain('5 sources')
  })

  it('states answerability instead of zero percentages when nothing was retrieved', () => {
    const quality = buildAnswerQuality({
      // The shape a skipped judge produces: floats coerced to zero.
      review: { groundedness_score: 0, completeness_score: 0, safety_score: 0 },
      sources: [],
    })

    expect(quality.kind).toBe('abstention')
    expect(quality.answerability).toBe('No supporting evidence')
    expect(quality.decision).toBe('Correctly abstained')
  })

  it('does not claim an abstention when passages were retrieved', () => {
    const quality = buildAnswerQuality({
      review: { groundedness_score: 0, completeness_score: 0, safety_score: 0 },
      sources: [{}, {}],
    })

    expect(quality.kind).toBe('summary')
    expect(quality.parts).toEqual(['2 sources'])
  })

  it('flags a failed review', () => {
    const quality = buildAnswerQuality({
      review: { verdict: 'fail', groundedness_score: 0.2 },
      sources: [{}],
    })

    expect(quality.tone).toBe('error')
    expect(quality.parts).toContain('Review failed')
  })

  it('treats an all-zero review as unmeasured', () => {
    expect(hasMeasuredScores({ groundedness_score: 0, completeness_score: 0, safety_score: 0 })).toBe(false)
    expect(hasMeasuredScores({ groundedness_score: 0.4 })).toBe(true)
    expect(hasMeasuredScores(null)).toBe(false)
  })

  it('never renders an unmeasured score as a number', () => {
    expect(toPercent(undefined)).toBeNull()
    expect(formatScore(undefined)).toBe('—')
    expect(formatScore(0.917)).toBe('92%')
  })
})
