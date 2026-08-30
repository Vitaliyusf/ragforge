/**
 * OBS-UX-01 — cross-screen deep links.
 *
 * The contract worth protecting is the refusal: a builder must return null
 * whenever the identifier it was handed is not one, because a link that lands
 * on an unfiltered page teaches the operator that the link means nothing.
 */
import { describe, expect, it } from 'vitest'

import {
  DEEP_LINK_KIND,
  LOG_SERVICES,
  LOG_SEVERITIES,
  conversationLink,
  documentLink,
  isUsableIdentifier,
  logsLinkForCorrelation,
  logsLinkForService,
} from './deepLinks'

describe('isUsableIdentifier', () => {
  it('rejects the zero-UUID placeholder a backend never filled in', () => {
    expect(isUsableIdentifier('00000000-0000-0000-0000-000000000000')).toBe(false)
    expect(isUsableIdentifier('----')).toBe(false)
  })

  it('rejects absent and blank values', () => {
    expect(isUsableIdentifier(null)).toBe(false)
    expect(isUsableIdentifier('')).toBe(false)
    expect(isUsableIdentifier('   ')).toBe(false)
  })

  it('accepts a real identifier', () => {
    expect(isUsableIdentifier('trace-9f2c')).toBe(true)
  })
})

describe('logsLinkForCorrelation', () => {
  it('filters every service to the identifier, at every severity', () => {
    const link = logsLinkForCorrelation({ id: 'trace-9f2c' })

    expect(link.kind).toBe(DEEP_LINK_KIND.LOGS)
    expect(link.destination).toBe('logs')
    expect(link.logs.textFilter).toBe('trace-9f2c')
    expect(link.logs.services).toEqual([...LOG_SERVICES])
    expect(link.logs.severities).toEqual([...LOG_SEVERITIES])
  })

  it('says it is searching a buffer rather than a trace store', () => {
    const link = logsLinkForCorrelation({ id: 'trace-9f2c' })
    expect(link.title).toMatch(/no longer in the buffer/i)
  })

  it('drops a service the log route would refuse to serve', () => {
    const link = logsLinkForCorrelation({ id: 'trace-9f2c', services: ['rag', 'nope'] })
    expect(link.logs.services).toEqual(['rag'])
  })

  it('offers nothing for a placeholder id', () => {
    expect(logsLinkForCorrelation({ id: '0000-0000' })).toBeNull()
    expect(logsLinkForCorrelation({ id: null })).toBeNull()
  })
})

describe('logsLinkForService', () => {
  it('narrows to what a degraded service is complaining about', () => {
    const link = logsLinkForService('rag')

    expect(link.logs.services).toEqual(['rag'])
    expect(link.logs.severities).toEqual(['error', 'warning'])
    expect(link.logs.textFilter).toBe('')
  })

  it('offers nothing for a service the log route does not serve', () => {
    expect(logsLinkForService('prometheus')).toBeNull()
    expect(logsLinkForService(undefined)).toBeNull()
  })
})

describe('conversationLink', () => {
  it('routes to the conversation the turn was recorded in', () => {
    expect(conversationLink('chat-42').route).toBe('/chat/chat-42')
  })

  it('escapes an id rather than letting it change the route shape', () => {
    expect(conversationLink('a/b').route).toBe('/chat/a%2Fb')
  })

  it('offers nothing without a conversation id', () => {
    expect(conversationLink(null)).toBeNull()
  })
})

describe('documentLink', () => {
  it('carries the file id as the intent the document library filters on', () => {
    const link = documentLink('file-7', 'contract.pdf')

    expect(link.destination).toBe('files')
    expect(link.intent).toEqual({ kind: DEEP_LINK_KIND.DOCUMENT, query: 'file-7' })
    expect(link.title).toMatch(/contract\.pdf/)
  })

  it('offers nothing without a file id', () => {
    expect(documentLink(null, 'contract.pdf')).toBeNull()
  })
})
