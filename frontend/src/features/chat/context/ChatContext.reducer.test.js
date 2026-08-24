import { describe, expect, it } from 'vitest'
import { chatRuntimeReducer, initialRuntimeState } from './ChatContext'

/**
 * These tests pin the core guarantee of branch 2: runtime state is keyed by
 * conversation, so a turn belonging to chat A can never mutate chat B's window.
 */

function makeTurn(conversationId, turnId) {
  return {
    turnId,
    conversationId,
    requestId: `req-${turnId}`,
    traceId: `trace-${turnId}`,
    mode: 'regular',
    status: 'connecting',
    streamText: '',
    finalAnswer: '',
    latestStatus: null,
    statusEvents: [],
    traceEvents: [],
    debugPayloads: {},
    answerReview: null,
    sources: [],
    retrievalSummary: null,
    feedback: {
      answer: { status: 'idle', error: null, payload: null },
      flow: { status: 'idle', error: null, payload: null },
    },
    error: null,
    userMessageId: `user-${turnId}`,
    assistantMessageId: `assistant-${turnId}`,
  }
}

function startTurn(state, conversationId, turnId) {
  const turn = makeTurn(conversationId, turnId)
  return chatRuntimeReducer(state, {
    type: 'TURN_STARTED',
    conversationId,
    turn,
    userMessage: {
      id: turn.userMessageId,
      turnId,
      sender: 'You',
      text: 'question',
      metadata: {},
    },
    assistantMessage: {
      id: turn.assistantMessageId,
      turnId,
      sender: 'Assistant',
      text: '',
      isLoading: true,
      metadata: {},
    },
  })
}

function assistantText(state, conversationId, turnId) {
  const bucket = state.conversations[conversationId]
  return bucket.messages.find((m) => m.id === `assistant-${turnId}`)?.text
}

describe('chatRuntimeReducer — per-conversation isolation', () => {
  it('starts turns in separate conversation buckets', () => {
    let state = initialRuntimeState
    state = startTurn(state, 'A', 't-a')
    state = startTurn(state, 'B', 't-b')

    expect(Object.keys(state.conversations).sort()).toEqual(['A', 'B'])
    expect(state.conversations.A.messages).toHaveLength(2)
    expect(state.conversations.B.messages).toHaveLength(2)
    expect(state.conversations.A.activeTurnId).toBe('t-a')
    expect(state.conversations.B.activeTurnId).toBe('t-b')
  })

  it('routes streamed tokens only to the owning conversation', () => {
    let state = initialRuntimeState
    state = startTurn(state, 'A', 't-a')
    state = startTurn(state, 'B', 't-b')

    state = chatRuntimeReducer(state, {
      type: 'TURN_TOKEN', conversationId: 'A', turnId: 't-a', delta: 'hello from A',
    })

    expect(assistantText(state, 'A', 't-a')).toBe('hello from A')
    expect(assistantText(state, 'B', 't-b')).toBe('')
    expect(state.conversations.B.chatState).not.toBe('streaming')
  })

  it('finalizes the owning conversation without touching the other', () => {
    let state = initialRuntimeState
    state = startTurn(state, 'A', 't-a')
    state = startTurn(state, 'B', 't-b')

    state = chatRuntimeReducer(state, {
      type: 'TURN_DONE',
      conversationId: 'A',
      turnId: 't-a',
      event: { data: { final_answer: 'A answer' }, timestamp: '2026-01-01T00:00:00Z' },
    })

    expect(assistantText(state, 'A', 't-a')).toBe('A answer')
    expect(state.conversations.A.chatState).toBe('done')
    expect(state.conversations.A.activeTurnId).toBeNull()
    // B is completely untouched: still connecting, still empty.
    expect(state.conversations.B.activeTurnId).toBe('t-b')
    expect(assistantText(state, 'B', 't-b')).toBe('')
  })

  it('does not clobber an in-flight bucket when history loads', () => {
    let state = initialRuntimeState
    state = startTurn(state, 'A', 't-a')
    state = chatRuntimeReducer(state, {
      type: 'TURN_TOKEN', conversationId: 'A', turnId: 't-a', delta: 'partial',
    })

    // A late history fetch for A (still streaming) must be ignored.
    state = chatRuntimeReducer(state, {
      type: 'HISTORY_LOADED', conversationId: 'A', messages: [],
    })

    expect(assistantText(state, 'A', 't-a')).toBe('partial')
    expect(state.conversations.A.activeTurnId).toBe('t-a')
  })

  it('loads history into a fresh conversation bucket', () => {
    const state = chatRuntimeReducer(initialRuntimeState, {
      type: 'HISTORY_LOADED',
      conversationId: 'C',
      messages: [{ id: 'm1', sender: 'You', text: 'hi' }],
    })

    expect(state.conversations.C.messages).toEqual([{ id: 'm1', sender: 'You', text: 'hi' }])
    expect(state.conversations.C.activeTurnId).toBeNull()
  })

  it('removes only the targeted conversation bucket', () => {
    let state = initialRuntimeState
    state = startTurn(state, 'A', 't-a')
    state = startTurn(state, 'B', 't-b')

    state = chatRuntimeReducer(state, { type: 'REMOVE_CONVERSATION', conversationId: 'A' })

    expect(state.conversations.A).toBeUndefined()
    expect(state.conversations.B).toBeDefined()
  })
})
