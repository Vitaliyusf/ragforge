import { beforeEach, describe, expect, it, vi } from 'vitest'

let fakeSocket

function createEmitter() {
  const listeners = new Map()

  const add = (eventName, callback, once = false) => {
    const entries = listeners.get(eventName) || []
    listeners.set(eventName, [...entries, { callback, once }])
  }

  return {
    on(eventName, callback) {
      add(eventName, callback, false)
    },
    once(eventName, callback) {
      add(eventName, callback, true)
    },
    off(eventName, callback) {
      if (!listeners.has(eventName)) return
      if (!callback) {
        listeners.delete(eventName)
        return
      }
      listeners.set(
        eventName,
        (listeners.get(eventName) || []).filter((entry) => entry.callback !== callback)
      )
    },
    trigger(eventName, payload) {
      const entries = [...(listeners.get(eventName) || [])]
      entries.forEach((entry) => {
        entry.callback(payload)
        if (entry.once) {
          this.off(eventName, entry.callback)
        }
      })
    },
  }
}

function createFakeSocket() {
  const emitter = createEmitter()
  const manager = createEmitter()

  return {
    connected: false,
    emitted: [],
    io: manager,
    on: emitter.on.bind(emitter),
    once: emitter.once.bind(emitter),
    off: emitter.off.bind(emitter),
    emit: vi.fn(function emit(eventName, payload) {
      this.emitted.push({ eventName, payload })
    }),
    connect: vi.fn(),
    disconnect: vi.fn(function disconnect() {
      this.connected = false
    }),
    trigger(eventName, payload) {
      if (eventName === 'connect') {
        this.connected = true
      }
      if (eventName === 'disconnect') {
        this.connected = false
      }
      emitter.trigger(eventName, payload)
    },
    triggerManager(eventName, payload) {
      manager.trigger(eventName, payload)
    },
  }
}

vi.mock('socket.io-client', () => ({
  io: vi.fn(() => fakeSocket),
}))

async function loadSocketService() {
  const module = await import('./socketService')
  return module.default
}

function createEnvelope(type, requestId, data) {
  return {
    type,
    request_id: requestId,
    trace_id: 'trace-1',
    conversation_id: 'chat-1',
    turn_id: 'turn-1',
    timestamp: '2026-03-17T00:00:00Z',
    data,
  }
}

describe('socketService', () => {
  beforeEach(() => {
    fakeSocket = createFakeSocket()
    vi.resetModules()
  })

  it('emits direct RAG questions and resolves only allowed runtime events', async () => {
    const socketService = await loadSocketService()
    const statusHandler = vi.fn()
    const traceHandler = vi.fn()
    const tokenHandler = vi.fn()
    const reviewHandler = vi.fn()

    const connectionPromise = socketService.connect()
    fakeSocket.trigger('connect')
    await connectionPromise

    const requestPromise = socketService.askQuestion(
      {
        question: 'Hello',
        mode: 'quick',
        request_id: 'req-1',
        conversation_id: 'chat-1',
      },
      {
        onStatus: statusHandler,
        onTrace: traceHandler,
        onToken: tokenHandler,
        onAnswerReview: reviewHandler,
      }
    )

    await Promise.resolve()

    expect(fakeSocket.emit).toHaveBeenCalledWith(
      'question',
      expect.objectContaining({
        question: 'Hello',
        mode: 'regular',
        request_id: 'req-1',
        conversation_id: 'chat-1',
      })
    )

    fakeSocket.trigger('status', createEnvelope('status', 'req-1', { phase: 'retrieval' }))
    fakeSocket.trigger('trace', createEnvelope('trace', 'req-1', { node: 'planner', latency: 12 }))
    fakeSocket.trigger('token', createEnvelope('token', 'req-1', { text_delta: 'Hello ' }))
    fakeSocket.trigger('answer_review', createEnvelope('answer_review', 'req-1', { verdict: 'pass' }))

    const doneEvent = createEnvelope('done', 'req-1', { final_answer: 'Hello world' })
    fakeSocket.trigger('done', doneEvent)

    await expect(requestPromise).resolves.toEqual(doneEvent)
    expect(statusHandler).toHaveBeenCalledTimes(1)
    expect(traceHandler).toHaveBeenCalledTimes(1)
    expect(tokenHandler).toHaveBeenCalledTimes(1)
    expect(reviewHandler).toHaveBeenCalledTimes(1)
  })

  it('reports reconnect state changes and rejects interrupted in-flight requests', async () => {
    const socketService = await loadSocketService()
    const statuses = []
    socketService.onStatusChange((status) => {
      statuses.push(status)
    })

    const connectionPromise = socketService.connect()
    fakeSocket.trigger('connect')
    await connectionPromise

    const requestPromise = socketService.askQuestion({
      question: 'Need reconnect handling',
      mode: 'extended',
      request_id: 'req-2',
      conversation_id: 'chat-1',
    })

    await Promise.resolve()

    fakeSocket.triggerManager('reconnect_attempt')
    fakeSocket.trigger('disconnect')
    fakeSocket.triggerManager('reconnect_failed')

    await expect(requestPromise).rejects.toThrow(/WebSocket connection interrupted/i)
    expect(statuses).toContain('connecting')
    expect(statuses).toContain('failed')
  })

  it('rejects on runtime error events and marks the error as already handled', async () => {
    const socketService = await loadSocketService()
    const onError = vi.fn()

    const connectionPromise = socketService.connect()
    fakeSocket.trigger('connect')
    await connectionPromise

    const requestPromise = socketService.askQuestion(
      {
        question: 'Trigger runtime error',
        mode: 'regular',
        request_id: 'req-3',
        conversation_id: 'chat-1',
      },
      { onError }
    )

    await Promise.resolve()

    const runtimeErrorEvent = createEnvelope('error', 'req-3', { message: 'Model backend failed' })
    fakeSocket.trigger('error', runtimeErrorEvent)

    await expect(requestPromise).rejects.toMatchObject({
      message: 'Model backend failed',
      runtimeHandled: true,
      runtimeEvent: runtimeErrorEvent,
    })
    expect(onError).toHaveBeenCalledWith(runtimeErrorEvent)
  })
})
