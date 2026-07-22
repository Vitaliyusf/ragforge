/** Socket.IO service for direct RAG chat and feedback events */
import { io } from 'socket.io-client'
import { config } from '@/lib/config'
import { normalizeChatMode } from '@/features/chat/utils/chatMode'
import { createAppError, normalizeError } from '@/lib/http/errors'
import { logger } from '@/lib/logger'
import authService from '@/features/auth/services/authService'

const ALLOWED_RUNTIME_EVENTS = ['status', 'trace', 'token', 'answer_review', 'done', 'error']
const FEEDBACK_EVENTS = new Set(['answer_feedback', 'flow_feedback'])
const CONNECTION_TIMEOUT_MS = 10000
const REGULAR_TIMEOUT_MS = 120000
const EXTENDED_TIMEOUT_MS = 300000

function createRuntimeError(message, runtimeEvent = null) {
  return createAppError(message, {
    type: 'websocket',
    code: runtimeEvent?.data?.code || 'WEBSOCKET_RUNTIME_ERROR',
    origin: runtimeEvent?.data?.origin || null,
    retryable: runtimeEvent?.data?.retryable || false,
    request_id: runtimeEvent?.request_id || null,
    trace_id: runtimeEvent?.trace_id || null,
    correlation_id: runtimeEvent?.data?.correlation_id || null,
    details: runtimeEvent?.data?.details || null,
    runtimeEvent,
    runtimeHandled: Boolean(runtimeEvent),
    payload: runtimeEvent,
  })
}

class SocketService {
  constructor() {
    this.socket = null
    this.isConnected = false
    this.isConnecting = false
    this.connectionStatus = 'disconnected'
    this.connectionPromise = null
    this.statusCallbacks = new Set()
    this.listeners = new Map()
    this.lastConnectionError = null
  }

  _notifyStatusChange() {
    this.statusCallbacks.forEach((callback) => {
      try {
        callback(this.connectionStatus, this.isConnected)
      } catch (error) {
        logger.error('Socket status callback failed', { error: normalizeError(error) })
      }
    })
  }

  _setStatus(status) {
    if (this.connectionStatus === status) return
    this.connectionStatus = status
    this._notifyStatusChange()
  }

  _ensureSocket() {
    if (this.socket) return

    this.socket = io(config.ragWsUrl, {
      transports: ['websocket'],
      autoConnect: false,
      reconnection: true,
      reconnectionAttempts: 5,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: CONNECTION_TIMEOUT_MS,
      forceNew: false,
      auth: async (callback) => {
        try {
          const response = await authService.getSocketTicket()
          callback({ ticket: response?.ticket })
        } catch (_) {
          callback({})
        }
      },
    })

    this.socket.on('connect', () => {
      this.isConnected = true
      this.isConnecting = false
      this.lastConnectionError = null
      this._setStatus('connected')
    })

    this.socket.on('disconnect', () => {
      this.isConnected = false
      this.isConnecting = false
      this._setStatus('disconnected')
    })

    this.socket.on('connect_error', (error) => {
      this.isConnected = false
      this.lastConnectionError = normalizeError(error instanceof Error ? error : new Error(String(error)))
      if (this.isConnecting) {
        this._setStatus('connecting')
      }
    })

    this.socket.io.on('reconnect_attempt', () => {
      this.isConnecting = true
      this._setStatus('connecting')
    })

    this.socket.io.on('reconnect_failed', () => {
      this.isConnected = false
      this.isConnecting = false
      this._setStatus('failed')
    })

    this.listeners.forEach((callbacks, eventName) => {
      callbacks.forEach((callback) => {
        this.socket.on(eventName, callback)
      })
    })
  }

  connect() {
    if (this.socket?.connected || this.isConnected) {
      this.isConnected = true
      this.isConnecting = false
      this._setStatus('connected')
      return Promise.resolve(this.socket)
    }

    if (this.connectionPromise) {
      return this.connectionPromise
    }

    this._ensureSocket()
    this.isConnecting = true
    this._setStatus('connecting')

    this.connectionPromise = new Promise((resolve, reject) => {
      let settled = false
      let timeoutId = null

      const cleanup = () => {
        if (timeoutId) {
          clearTimeout(timeoutId)
          timeoutId = null
        }
        this.socket?.off('connect', handleConnect)
        this.socket?.io?.off('reconnect_failed', handleReconnectFailed)
      }

      const finish = (fn, value) => {
        if (settled) return
        settled = true
        cleanup()
        this.connectionPromise = null
        fn(value)
      }

      const handleConnect = () => {
        finish(resolve, this.socket)
      }

      const handleReconnectFailed = () => {
        this.isConnecting = false
        this._setStatus('failed')
        finish(reject, this.lastConnectionError || createAppError('WebSocket reconnection failed', { type: 'websocket', code: 'WEBSOCKET_RECONNECT_FAILED', retryable: true }))
      }

      timeoutId = setTimeout(() => {
        this.isConnecting = false
        this._setStatus('failed')
        finish(reject, this.lastConnectionError || createAppError('WebSocket connection timeout', { type: 'websocket', code: 'WEBSOCKET_CONNECTION_TIMEOUT', retryable: true }))
      }, CONNECTION_TIMEOUT_MS)

      this.socket.once('connect', handleConnect)
      this.socket.io.once('reconnect_failed', handleReconnectFailed)

      try {
        this.socket.connect()
      } catch (error) {
        this.isConnecting = false
        this._setStatus('failed')
        finish(reject, normalizeError(error instanceof Error ? error : new Error(String(error))))
      }
    })

    return this.connectionPromise
  }

  disconnect() {
    if (!this.socket) return
    this.socket.disconnect()
    this.socket = null
    this.connectionPromise = null
    this.isConnected = false
    this.isConnecting = false
    this._setStatus('disconnected')
  }

  async askQuestion(payload, handlers = {}) {
    const normalizedPayload = {
      ...payload,
      mode: normalizeChatMode(payload?.mode),
    }

    await this.connect()
    if (!this.socket?.connected) {
      throw createAppError('WebSocket not connected', { type: 'websocket', code: 'WEBSOCKET_NOT_CONNECTED', retryable: true })
    }

    return new Promise((resolve, reject) => {
      let settled = false
      let timeoutId = null

      const cleanup = () => {
        if (timeoutId) {
          clearTimeout(timeoutId)
          timeoutId = null
        }

        this.socket?.off('disconnect', handleDisconnect)
        ALLOWED_RUNTIME_EVENTS.forEach((eventName) => {
          this.socket?.off(eventName, runtimeHandlers[eventName])
        })
      }

      const finish = (fn, value) => {
        if (settled) return
        settled = true
        cleanup()
        fn(value)
      }

      const handleDisconnect = () => {
        finish(reject, createAppError('WebSocket connection interrupted', { type: 'websocket', code: 'WEBSOCKET_INTERRUPTED', retryable: true, request_id: normalizedPayload.request_id }))
      }

      const runtimeHandlers = {
        status: (event) => {
          if (event?.request_id !== normalizedPayload.request_id) return
          handlers.onStatus?.(event)
        },
        trace: (event) => {
          if (event?.request_id !== normalizedPayload.request_id) return
          handlers.onTrace?.(event)
        },
        token: (event) => {
          if (event?.request_id !== normalizedPayload.request_id) return
          handlers.onToken?.(event)
        },
        answer_review: (event) => {
          if (event?.request_id !== normalizedPayload.request_id) return
          handlers.onAnswerReview?.(event)
        },
        done: (event) => {
          if (event?.request_id !== normalizedPayload.request_id) return
          handlers.onDone?.(event)
          finish(resolve, event)
        },
        error: (event) => {
          if (event?.request_id !== normalizedPayload.request_id) return
          handlers.onError?.(event)
          finish(reject, createRuntimeError(event?.data?.message || 'Error processing question', event))
        },
      }

      timeoutId = setTimeout(() => {
        finish(reject, createAppError('Request timeout', { type: 'websocket', code: 'WEBSOCKET_REQUEST_TIMEOUT', retryable: true, request_id: normalizedPayload.request_id }))
      }, normalizedPayload.mode === 'extended' ? EXTENDED_TIMEOUT_MS : REGULAR_TIMEOUT_MS)

      this.socket.on('disconnect', handleDisconnect)
      ALLOWED_RUNTIME_EVENTS.forEach((eventName) => {
        this.socket.on(eventName, runtimeHandlers[eventName])
      })

      try {
        this.socket.emit('question', normalizedPayload)
      } catch (error) {
        finish(reject, normalizeError(error instanceof Error ? error : new Error(String(error))))
      }
    })
  }

  async sendFeedback(eventName, payload) {
    if (!FEEDBACK_EVENTS.has(eventName)) {
      throw new Error(`Unsupported feedback event: ${eventName}`)
    }

    await this.connect()
    if (!this.socket?.connected) {
      throw createAppError('WebSocket not connected', { type: 'websocket', code: 'WEBSOCKET_NOT_CONNECTED', retryable: true })
    }

    this.socket.emit(eventName, payload)
    return { sent: true, eventName }
  }

  on(eventName, callback) {
    const callbacks = this.listeners.get(eventName) || new Set()
    callbacks.add(callback)
    this.listeners.set(eventName, callbacks)
    this.socket?.on(eventName, callback)
  }

  off(eventName, callback) {
    const callbacks = this.listeners.get(eventName)
    if (callbacks) {
      callbacks.delete(callback)
      if (callbacks.size === 0) {
        this.listeners.delete(eventName)
      }
    }
    this.socket?.off(eventName, callback)
  }

  getConnectionStatus() {
    return this.isConnected
  }

  getDetailedStatus() {
    return this.connectionStatus
  }

  onStatusChange(callback) {
    this.statusCallbacks.add(callback)
    callback(this.connectionStatus, this.isConnected)
    return () => {
      this.statusCallbacks.delete(callback)
    }
  }
}

export default new SocketService()
