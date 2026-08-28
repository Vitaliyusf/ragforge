import { describe, expect, it } from 'vitest'
import {
  computeEffectiveStatus,
  getFileStatusTone,
  hasReviewPending,
  normalizeFileStatus,
} from './fileStatus'

describe('normalizeFileStatus', () => {
  it('collapses the server spellings onto one vocabulary', () => {
    for (const raw of ['started', 'processing', 'resuming', 'running']) {
      expect(normalizeFileStatus(raw)).toBe('processing')
    }
    for (const raw of ['complete', 'completed', 'ready', 'done']) {
      expect(normalizeFileStatus(raw)).toBe('complete')
    }
    expect(normalizeFileStatus('  AWAITING_REVIEW ')).toBe('awaiting_review')
    expect(normalizeFileStatus(null)).toBe('unknown')
  })
})

describe('computeEffectiveStatus', () => {
  it('trusts a terminal top-level status', () => {
    expect(computeEffectiveStatus({ status: 'rejected', stage: { a: 'done' } })).toBe('rejected')
  })

  it('promotes a stale processing status once every stage finished', () => {
    const file = { status: 'processing', stage: { parse: 'done', embed: 'skipped' } }
    expect(computeEffectiveStatus(file)).toBe('complete')
  })

  it('reports an errored stage', () => {
    expect(computeEffectiveStatus({ status: 'processing', stage: { embed: 'error' } })).toBe('error')
  })

  it('leaves an unfinished pipeline alone', () => {
    expect(computeEffectiveStatus({ status: 'processing', stage: { embed: 'running' } })).toBe('processing')
  })
})

describe('tones', () => {
  it('maps states onto shared tones', () => {
    expect(getFileStatusTone('complete')).toBe('success')
    // Something really is moving, so processing gets the live tone.
    expect(getFileStatusTone('running')).toBe('live')
    expect(getFileStatusTone('error')).toBe('danger')
    expect(getFileStatusTone('rejected')).toBe('danger')
    expect(getFileStatusTone('awaiting_review')).toBe('warning')
    expect(getFileStatusTone('whatever')).toBe('neutral')
  })
})

describe('hasReviewPending', () => {
  it('accepts either the status or the review field', () => {
    expect(hasReviewPending({ status: 'awaiting_review' })).toBe(true)
    expect(hasReviewPending({ status: 'complete', review_status: 'pending' })).toBe(true)
    expect(hasReviewPending({ status: 'complete' })).toBe(false)
  })
})
