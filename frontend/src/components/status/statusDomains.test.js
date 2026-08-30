/**
 * The status taxonomy: five vocabularies that must not leak into each other.
 */
import { describe, expect, it } from 'vitest'

import { STATUS_DOMAINS, describeStatus, statesOf } from './statusDomains'
import { STATUS_TONE } from './statusTone'

const { RESOURCE, SERVICE, EXECUTION, CONNECTIVITY, REVIEW } = STATUS_DOMAINS

describe('domains', () => {
  it('carries exactly the states the product model defines', () => {
    expect(statesOf(RESOURCE)).toEqual(['ready', 'processing', 'failed'])
    expect(statesOf(SERVICE)).toEqual(['healthy', 'degraded', 'unhealthy'])
    expect(statesOf(EXECUTION)).toEqual([
      'queued',
      'running',
      'completed',
      'partial',
      'failed',
      'skipped',
    ])
    expect(statesOf(CONNECTIVITY)).toEqual(['connected', 'disconnected'])
    expect(statesOf(REVIEW)).toEqual(['passed', 'needs_review', 'failed'])
  })

  it('gives every state a canonical label and a real tone', () => {
    for (const domain of Object.values(STATUS_DOMAINS)) {
      for (const state of statesOf(domain)) {
        const status = describeStatus(domain, state)
        expect(status.label).toBeTruthy()
        expect(STATUS_TONE[status.tone]).toBeDefined()
        expect(status.known).toBe(true)
      }
    }
  })

  it('rejects a domain it does not define', () => {
    expect(() => describeStatus('vibes', 'good')).toThrow(/Unknown status domain/)
  })
})

describe('domains do not mix', () => {
  it('will not answer a resource question with a service word', () => {
    expect(describeStatus(RESOURCE, 'healthy').known).toBe(false)
    expect(describeStatus(RESOURCE, 'healthy').label).toBe('Unknown')
  })

  it('will not answer a service question with an execution word', () => {
    expect(describeStatus(SERVICE, 'queued').known).toBe(false)
    expect(describeStatus(SERVICE, 'running').known).toBe(false)
  })

  it('will not answer a connectivity question with a review word', () => {
    expect(describeStatus(CONNECTIVITY, 'passed').known).toBe(false)
  })

  it('reads a shared spelling differently per domain', () => {
    // "pending" is a queued run, an in-flight document, and an unreviewed
    // one. One flat alias table would have let one domain answer for another.
    expect(describeStatus(EXECUTION, 'pending').state).toBe('queued')
    expect(describeStatus(RESOURCE, 'pending').state).toBe('processing')
    expect(describeStatus(REVIEW, 'pending').state).toBe('needs_review')
  })
})

describe('backend spellings', () => {
  it('maps the vocabularies services actually emit', () => {
    expect(describeStatus(EXECUTION, 'interrupted').label).toBe('Partial')
    expect(describeStatus(EXECUTION, 'success').label).toBe('Completed')
    expect(describeStatus(RESOURCE, 'error').label).toBe('Failed')
    expect(describeStatus(RESOURCE, 'indexed').label).toBe('Ready')
    expect(describeStatus(CONNECTIVITY, 'offline').label).toBe('Disconnected')
    expect(describeStatus(REVIEW, 'needs-review').label).toBe('Needs review')
  })

  it('normalises case and spacing rather than failing on it', () => {
    expect(describeStatus(REVIEW, 'Needs Review').state).toBe('needs_review')
    expect(describeStatus(SERVICE, ' HEALTHY ').state).toBe('healthy')
  })

  it('reports the unmeasured as Unknown instead of inventing a good state', () => {
    for (const domain of Object.values(STATUS_DOMAINS)) {
      const status = describeStatus(domain, null)
      expect(status.label).toBe('Unknown')
      expect(status.known).toBe(false)
      expect(status.tone).toBe('neutral')
    }
  })
})

describe('tones', () => {
  it('never dresses a partial or degraded result as a success', () => {
    expect(describeStatus(EXECUTION, 'partial').tone).toBe('warning')
    expect(describeStatus(SERVICE, 'degraded').tone).toBe('warning')
    expect(describeStatus(EXECUTION, 'completed').tone).toBe('success')
  })

  it('reserves the moving tone for work that is actually moving', () => {
    expect(STATUS_TONE[describeStatus(EXECUTION, 'running').tone].live).toBe(true)
    expect(STATUS_TONE[describeStatus(RESOURCE, 'processing').tone].live).toBe(true)
    expect(STATUS_TONE[describeStatus(EXECUTION, 'queued').tone].live).toBe(false)
  })
})
