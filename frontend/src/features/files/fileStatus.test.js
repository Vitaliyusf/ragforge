import { describe, expect, it } from 'vitest'
import {
  computeEffectiveStatus,
  getEffectiveStatusLabel,
  getEffectiveStatusTone,
  getFileStatusLabel,
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

describe('labels and tones', () => {
  it('labels every known state', () => {
    expect(getFileStatusLabel('awaiting_review')).toBe('Awaiting Review')
    expect(getFileStatusLabel('running')).toBe('Processing')
    expect(getEffectiveStatusLabel({ status: 'processing', stage: { a: 'done' } })).toBe('Complete')
  })

  it('humanises an unrecognised state rather than dropping it', () => {
    expect(getFileStatusLabel('some_new_state')).toBe('some new state')
  })

  it('maps states onto shared tones', () => {
    expect(getFileStatusTone('complete')).toBe('success')
    expect(getFileStatusTone('error')).toBe('danger')
    expect(getFileStatusTone('rejected')).toBe('danger')
    expect(getFileStatusTone('awaiting_review')).toBe('warning')
    expect(getFileStatusTone('whatever')).toBe('neutral')
    expect(getEffectiveStatusTone({ status: 'processing', stage: { a: 'error' } })).toBe('danger')
  })
})

describe('hasReviewPending', () => {
  it('accepts either the status or the review field', () => {
    expect(hasReviewPending({ status: 'awaiting_review' })).toBe(true)
    expect(hasReviewPending({ status: 'complete', review_status: 'pending' })).toBe(true)
    expect(hasReviewPending({ status: 'complete' })).toBe(false)
  })
})
