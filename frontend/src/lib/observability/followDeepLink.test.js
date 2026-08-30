/**
 * OBS-UX-01 — what following a link actually does.
 *
 * Each kind of jump has to arrive *already narrowed*. Arriving at an
 * unfiltered log stream, or at Chat without the conversation open, is the
 * failure this covers.
 */
import { describe, expect, it, vi } from 'vitest'

import { conversationLink, documentLink, logsLinkForService } from './deepLinks'
import { createDeepLinkFollower } from './followDeepLink'

function harness() {
  const dispatch = vi.fn()
  const router = { push: vi.fn() }
  const navigate = vi.fn()
  const logActions = {
    setSelectedServices: (payload) => ({ type: 'logs/setSelectedServices', payload }),
    setSeverityFilter: (payload) => ({ type: 'logs/setSeverityFilter', payload }),
    setTextFilter: (payload) => ({ type: 'logs/setTextFilter', payload }),
  }
  const follow = createDeepLinkFollower({ dispatch, router, navigate, logActions })
  return { dispatch, router, navigate, follow }
}

describe('createDeepLinkFollower', () => {
  it('sets the log filters before opening the log workspace', () => {
    const { dispatch, navigate, follow } = harness()

    follow(logsLinkForService('rag'))

    expect(dispatch.mock.calls.map(([action]) => action)).toEqual([
      { type: 'logs/setSelectedServices', payload: ['rag'] },
      { type: 'logs/setSeverityFilter', payload: ['error', 'warning'] },
      { type: 'logs/setTextFilter', payload: '' },
    ])
    expect(navigate).toHaveBeenCalledWith('logs')
  })

  it('moves the route as well as the tab, because the route is what opens a chat', () => {
    const { router, navigate, follow } = harness()

    follow(conversationLink('chat-42'))

    expect(router.push).toHaveBeenCalledWith('/chat/chat-42')
    expect(navigate).toHaveBeenCalledWith('chat')
  })

  it('hands the document library the file it was asked about', () => {
    const { navigate, follow } = harness()

    follow(documentLink('file-7'))

    expect(navigate).toHaveBeenCalledWith('files', { kind: 'document', query: 'file-7' })
  })

  it('does nothing at all for a link a builder refused to build', () => {
    const { dispatch, router, navigate, follow } = harness()

    follow(null)

    expect(dispatch).not.toHaveBeenCalled()
    expect(router.push).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })
})
