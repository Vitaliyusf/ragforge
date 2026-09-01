import { describe, expect, it } from 'vitest'

import { HISTORY_MESSAGE_LIMIT } from './chatConstants'
import {
  buildPersistedAssistantMetadata,
  formatHistoryForPrompt,
  mapGatewayMessage,
} from './chatHelpers'

describe('formatHistoryForPrompt', () => {
  it('returns an empty string when there is no history', () => {
    expect(formatHistoryForPrompt([])).toBe('')
    expect(formatHistoryForPrompt(undefined)).toBe('')
  })

  it('formats sender/text pairs and drops blank messages', () => {
    const history = [
      { sender: 'You', text: 'hello' },
      { sender: 'Assistant', text: '   ' },
      { sender: 'Assistant', text: 'hi there' },
    ]
    expect(formatHistoryForPrompt(history)).toBe('[You]: hello\n[Assistant]: hi there')
  })

  it('keeps only the most recent HISTORY_MESSAGE_LIMIT messages', () => {
    const history = Array.from({ length: HISTORY_MESSAGE_LIMIT + 5 }, (_, index) => ({
      sender: 'You',
      text: `message-${index}`,
    }))
    const lines = formatHistoryForPrompt(history).split('\n')
    expect(lines).toHaveLength(HISTORY_MESSAGE_LIMIT)
    expect(lines[0]).toBe('[You]: message-5')
  })
})

describe('durable chat metadata', () => {
  it('builds a bounded TURN_DONE snapshot and excludes private/transient fields', () => {
    const metadata = buildPersistedAssistantMetadata(
      { requestId: 'request-local', traceId: 'trace-local', conversationId: 'chat-1', turnId: 'turn-1', mode: 'regular' },
      {
        request_id: 'request-done',
        trace_id: 'trace-done',
        conversation_id: 'chat-1',
        turn_id: 'turn-1',
        data: {
          review_summary: { verdict: 'pass', auth_token: 'never-store' },
          sources: [{ source_name: 'handbook.pdf', score: 0.9, text: 'private full chunk', text_preview: 'safe excerpt' }],
          retrieval_summary: { chunk_count: 1 },
          trace_summary: [{ node: 'retrieve', latency: 12 }],
          safe_debug_payloads: { visible_reasoning_summary: 'Short summary', generation_context: 'private chunks', password: 'never-store' },
          debug_payloads: { chain_of_thought: 'never-store' },
        },
      }
    )

    expect(metadata).toMatchObject({
      requestId: 'request-done',
      traceId: 'trace-done',
      turnId: 'turn-1',
      answerReview: { verdict: 'pass' },
      sources: [{ source_name: 'handbook.pdf', score: 0.9, text_preview: 'safe excerpt' }],
      retrievalSummary: { chunk_count: 1 },
      traceEvents: [{ node: 'retrieve', latency: 12 }],
      debugPayloads: { visible_reasoning_summary: 'Short summary' },
    })
    expect(JSON.stringify(metadata)).not.toContain('private full chunk')
    expect(JSON.stringify(metadata)).not.toContain('never-store')
    expect(JSON.stringify(metadata)).not.toContain('generation_context')
    expect(JSON.stringify(metadata)).not.toContain('chain_of_thought')
  })

  it('restores persisted metadata and treats legacy messages as empty metadata', () => {
    const restored = mapGatewayMessage({
      id: 'assistant-1',
      sender: 'Assistant',
      message: 'Answer',
      metadata: { turnId: 'turn-1', sources: [{ title: 'Guide' }] },
    })
    expect(restored.turnId).toBe('turn-1')
    expect(restored.metadata.sources).toEqual([{ title: 'Guide' }])
    expect(mapGatewayMessage({ id: 'legacy', sender: 'Assistant', message: 'Old' }).metadata).toEqual({})
  })
})
