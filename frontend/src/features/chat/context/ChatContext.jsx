'use client'

/**
 * Chat runtime provider for gateway-backed history plus direct `rag` streaming.
 *
 * The provider keeps persisted chat-history CRUD on the gateway boundary while
 * the active turn state machine consumes direct Socket.IO events from `rag`.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useDispatch } from 'react-redux'
import { chatDeleted as chatDeletedAction } from '@/store/slices/eventsSlice'
import chatService from '@/features/chat/services/chatService'
import socketService from '@/features/websocket/services/socketService'
import { normalizeChatMode } from '@/features/chat/utils/chatMode'

const ChatContext = createContext(null)

const HISTORY_MESSAGE_LIMIT = 10
const CHAT_MODE_STORAGE_KEY = 'ragforge-chat-mode'

const initialRuntimeState = {
  messages: [],
  turnsById: {},
  turnOrder: [],
  chatState: 'idle',
  activeTurnId: null,
}

function createId(prefix) {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`
}

function formatHistoryForPrompt(messages) {
  if (!messages?.length) return ''
  const recent = messages
    .filter((message) => (message.text || '').trim().length > 0)
    .slice(-HISTORY_MESSAGE_LIMIT)
  return recent.map((message) => `[${message.sender}]: ${message.text || ''}`).join('\n')
}

function mapGatewayMessage(message) {
  return {
    id: message.id || message.message_id || createId('history-message'),
    turnId: message.metadata?.turnId || null,
    sender: message.sender || (message.role === 'user' ? 'You' : 'Assistant'),
    text: message.message || message.text || message.content || '',
    timestamp: message.timestamp || message.created_at || null,
    isLoading: false,
    metadata: message.metadata || {},
  }
}

function buildAssistantMetadata(turn) {
  return {
    requestId: turn.requestId,
    traceId: turn.traceId,
    conversationId: turn.conversationId,
    turnId: turn.turnId,
    mode: turn.mode,
    historySent: turn.historySent || null,
    answerReview: turn.answerReview,
    traceEvents: turn.traceEvents,
    statusEvents: turn.statusEvents,
    debugPayloads: turn.debugPayloads,
    sources: turn.sources,
    retrievalSummary: turn.retrievalSummary,
    feedback: turn.feedback,
    error: turn.error,
  }
}

function updateMessage(messages, messageId, updater) {
  return messages.map((message) => {
    if (message.id !== messageId) return message
    const next = typeof updater === 'function' ? updater(message) : updater
    return { ...message, ...next }
  })
}

function updateTurn(state, turnId, updater, nextChatState = state.chatState) {
  const currentTurn = state.turnsById[turnId]
  if (!currentTurn) return state

  const nextTurn = updater(currentTurn)
  return {
    ...state,
    chatState: nextChatState,
    turnsById: {
      ...state.turnsById,
      [turnId]: nextTurn,
    },
  }
}

function chatRuntimeReducer(state, action) {
  switch (action.type) {
    case 'RESET':
      return initialRuntimeState

    case 'HISTORY_LOADED':
      return {
        ...initialRuntimeState,
        messages: action.messages,
      }

    case 'TURN_STARTED': {
      const { turn, userMessage, assistantMessage } = action
      return {
        ...state,
        chatState: 'connecting',
        activeTurnId: turn.turnId,
        turnOrder: [...state.turnOrder, turn.turnId],
        turnsById: {
          ...state.turnsById,
          [turn.turnId]: turn,
        },
        messages: [...state.messages, userMessage, assistantMessage],
      }
    }

    case 'TURN_STATUS': {
      return updateTurn(
        state,
        action.turnId,
        (turn) => ({
          ...turn,
          latestStatus: action.event.data || {},
          statusEvents: [...turn.statusEvents, action.event],
        }),
        state.chatState === 'streaming' ? 'streaming' : 'connecting'
      )
    }

    case 'TURN_TRACE': {
      return updateTurn(state, action.turnId, (turn) => {
        const nextTurn = {
          ...turn,
          traceEvents: [...turn.traceEvents, action.event.data || {}],
        }

        return nextTurn
      })
    }

    case 'TURN_TOKEN': {
      const currentTurn = state.turnsById[action.turnId]
      if (!currentTurn) return state

      const nextTurn = {
        ...currentTurn,
        status: 'streaming',
        streamText: `${currentTurn.streamText || ''}${action.delta}`,
      }

      return {
        ...state,
        chatState: 'streaming',
        turnsById: {
          ...state.turnsById,
          [action.turnId]: nextTurn,
        },
        messages: updateMessage(state.messages, currentTurn.assistantMessageId, (message) => ({
          text: `${message.text || ''}${action.delta}`,
          metadata: {
            ...message.metadata,
            ...buildAssistantMetadata(nextTurn),
          },
        })),
      }
    }

    case 'TURN_ANSWER_REVIEW': {
      const currentTurn = state.turnsById[action.turnId]
      if (!currentTurn) return state

      const nextTurn = {
        ...currentTurn,
        answerReview: action.event.data || null,
      }

      return {
        ...state,
        turnsById: {
          ...state.turnsById,
          [action.turnId]: nextTurn,
        },
        messages: updateMessage(state.messages, currentTurn.assistantMessageId, (message) => ({
          metadata: {
            ...message.metadata,
            ...buildAssistantMetadata(nextTurn),
          },
        })),
      }
    }

    case 'TURN_DONE': {
      const currentTurn = state.turnsById[action.turnId]
      if (!currentTurn) return state

      const data = action.event.data || {}
      const finalAnswer = data.final_answer || currentTurn.streamText || currentTurn.finalAnswer || ''
      const nextTurn = {
        ...currentTurn,
        status: 'done',
        finalAnswer,
        answerReview: data.review_summary || currentTurn.answerReview,
        traceEvents: Array.isArray(data.trace_summary) && data.trace_summary.length > 0
          ? data.trace_summary
          : currentTurn.traceEvents,
        debugPayloads: data.safe_debug_payloads || data.debug_payloads || currentTurn.debugPayloads,
        sources: data.sources || currentTurn.sources,
        retrievalSummary: data.retrieval_summary || currentTurn.retrievalSummary,
        doneEvent: action.event,
        error: null,
      }

      return {
        ...state,
        chatState: 'done',
        activeTurnId: null,
        turnsById: {
          ...state.turnsById,
          [action.turnId]: nextTurn,
        },
        messages: updateMessage(state.messages, currentTurn.assistantMessageId, (message) => ({
          text: finalAnswer,
          timestamp: action.event.timestamp || message.timestamp || new Date().toISOString(),
          isLoading: false,
          metadata: {
            ...message.metadata,
            ...buildAssistantMetadata(nextTurn),
          },
        })),
      }
    }

    case 'TURN_ERROR': {
      const currentTurn = state.turnsById[action.turnId]
      if (!currentTurn) return state

      const errorMessage = action.errorMessage || action.event?.data?.message || 'Error sending message'
      const nextTurn = {
        ...currentTurn,
        status: 'error',
        error: errorMessage,
        errorEvent: action.event || null,
      }

      return {
        ...state,
        chatState: 'error',
        activeTurnId: null,
        turnsById: {
          ...state.turnsById,
          [action.turnId]: nextTurn,
        },
        messages: updateMessage(state.messages, currentTurn.assistantMessageId, (message) => ({
          text: errorMessage,
          timestamp: action.event?.timestamp || new Date().toISOString(),
          isLoading: false,
          metadata: {
            ...message.metadata,
            ...buildAssistantMetadata(nextTurn),
          },
        })),
      }
    }

    case 'TURN_FEEDBACK_STATE': {
      const currentTurn = state.turnsById[action.turnId]
      if (!currentTurn) return state

      const nextTurn = {
        ...currentTurn,
        feedback: {
          ...currentTurn.feedback,
          [action.feedbackKey]: {
            ...(currentTurn.feedback[action.feedbackKey] || {}),
            status: action.status,
            error: action.error || null,
            payload: action.payload || currentTurn.feedback[action.feedbackKey]?.payload || null,
          },
        },
      }

      return {
        ...state,
        turnsById: {
          ...state.turnsById,
          [action.turnId]: nextTurn,
        },
        messages: updateMessage(state.messages, currentTurn.assistantMessageId, (message) => ({
          metadata: {
            ...message.metadata,
            ...buildAssistantMetadata(nextTurn),
          },
        })),
      }
    }

    default:
      return state
  }
}

export function ChatProvider({ children }) {
  const pathname = usePathname()
  const router = useRouter()
  const dispatch = useDispatch()
  const [runtimeState, dispatchRuntime] = useReducer(chatRuntimeReducer, initialRuntimeState)
  const messagesRef = useRef(runtimeState.messages)
  const skipNextMessageLoadRef = useRef(null)

  const [chats, setChats] = useState([])
  const [currentChatId, setCurrentChatId] = useState(null)
  const [loading, setLoading] = useState(false)
  const [chatsLoading, setChatsLoading] = useState(true)
  const [chatsError, setChatsError] = useState(null)
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState(null)
  const [defaultModel, setDefaultModel] = useState('default')
  const [wsConnectionStatus, setWsConnectionStatus] = useState('disconnected')
  const [answerMode, setAnswerModeState] = useState('regular')
  const [deletingChatIds, setDeletingChatIds] = useState(new Set())
  const [generatingTitleChatIds, setGeneratingTitleChatIds] = useState(new Set())

  useEffect(() => {
    messagesRef.current = runtimeState.messages
  }, [runtimeState.messages])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const persistedMode = window.localStorage.getItem(CHAT_MODE_STORAGE_KEY)
    if (persistedMode) {
      setAnswerModeState(normalizeChatMode(persistedMode))
    }
  }, [])

  const setAnswerMode = useCallback((mode) => {
    const normalized = normalizeChatMode(mode)
    setAnswerModeState(normalized)
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(CHAT_MODE_STORAGE_KEY, normalized)
    }
  }, [])

  useEffect(() => {
    const unsubscribe = socketService.onStatusChange((status) => {
      setWsConnectionStatus(status)
    })
    socketService.connect().catch(() => {
      // Surface connection state in the badge; no HTTP fallback is used.
    })
    return unsubscribe
  }, [])

  const loadChats = useCallback(async (isRetry = false) => {
    setChatsLoading(true)
    setChatsError(null)
    try {
      const data = await chatService.getChats()
      const chatList = data.chats || data.data?.chats || []
      setChats(Array.isArray(chatList) ? chatList : [])
    } catch (error) {
      const is504 =
        error?.status === 504 ||
        error?.statusCode === 504 ||
        (typeof error?.message === 'string' &&
          (error.message.includes('504') || error.message.toLowerCase().includes('gateway timeout')))
      const message = is504
        ? 'Chat history is unavailable. Please ensure the gateway and memory services are running.'
        : error?.message || 'Failed to load chats'
      if (is504 && !isRetry) {
        await new Promise((resolve) => setTimeout(resolve, 2500))
        return loadChats(true)
      }
      setChatsError(message)
      setChats([])
    } finally {
      setChatsLoading(false)
    }
  }, [])

  const loadMessages = useCallback(async (chatId) => {
    if (!chatId) {
      dispatchRuntime({ type: 'RESET' })
      return
    }

    setLoading(true)
    try {
      const data = await chatService.getMessages(chatId)
      const messageList = data.messages || data.data?.messages || []
      const formatted = (Array.isArray(messageList) ? messageList : []).map(mapGatewayMessage)
      dispatchRuntime({ type: 'HISTORY_LOADED', messages: formatted })
    } catch (error) {
      const is504 =
        error?.status === 504 ||
        error?.statusCode === 504 ||
        (typeof error?.message === 'string' &&
          (error.message.includes('504') || error.message.toLowerCase().includes('gateway timeout')))
      if (is504) {
        setChatsError('Chat history is unavailable. Please ensure the gateway and memory services are running.')
      }
      dispatchRuntime({ type: 'HISTORY_LOADED', messages: [] })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadChats()
  }, [loadChats])

  useEffect(() => {
    const chatIdFromPath = pathname?.match(/\/chat\/([^/]+)/)?.[1]
    if (chatIdFromPath) {
      setCurrentChatId(chatIdFromPath)
      return
    }

    setCurrentChatId(null)
    dispatchRuntime({ type: 'RESET' })
  }, [pathname])

  useEffect(() => {
    if (!currentChatId) return

    if (skipNextMessageLoadRef.current === currentChatId) {
      skipNextMessageLoadRef.current = null
      return
    }

    loadMessages(currentChatId)
  }, [currentChatId, loadMessages])

  const loadModels = useCallback(async () => {
    try {
      const data = await chatService.getModels()
      const modelList = data.models || data.data?.models || []
      if (Array.isArray(modelList) && modelList.length > 0) {
        setModels(modelList)
        if (!selectedModel && modelList[0]) {
          const name = typeof modelList[0] === 'object' ? modelList[0].name : modelList[0]
          setSelectedModel(name)
        }
        return
      }
      setModels([])
    } catch (_) {
      setModels([])
    }
  }, [selectedModel])

  useEffect(() => {
    loadModels()
  }, [loadModels])

  const createNewChat = useCallback(async () => {
    setLoading(true)
    try {
      const data = await chatService.createChat()
      const chatId = data.chat_id || data.id || data.data?.chat_id
      if (!chatId) return null

      const title = data.title || 'New Chat'
      setChats((prev) => [{ id: chatId, title, updated_at: new Date().toISOString() }, ...prev])
      // The new chat starts empty, so skip the message reload the pathname
      // effect would otherwise trigger once the URL lands on this id.
      skipNextMessageLoadRef.current = chatId
      dispatchRuntime({ type: 'RESET' })
      router.push(`/chat/${chatId}`)
      return chatId
    } catch (error) {
      console.error('Create chat error:', error)
      return null
    } finally {
      setLoading(false)
    }
  }, [router])

  // Selection is navigation: the pathname effect is the single writer of
  // currentChatId, so switching chats can never desync the URL from state.
  const selectChat = useCallback((chatId) => {
    if (!chatId || chatId === currentChatId) return
    router.push(`/chat/${chatId}`)
  }, [currentChatId, router])

  const refreshChatsAfterPersist = useCallback(async (chatId) => {
    try {
      const updated = await chatService.getChats()
      const chatList = updated.chats || updated.data?.chats || []
      setChats(Array.isArray(chatList) ? chatList : [])
    } catch (error) {
      console.error('Failed to refresh chats:', error)
      setChats((prev) => prev.map((chat) => (
        chat.id === chatId
          ? { ...chat, updated_at: new Date().toISOString() }
          : chat
      )))
    } finally {
      setGeneratingTitleChatIds((prev) => {
        const next = new Set(prev)
        next.delete(chatId)
        return next
      })
    }
  }, [])

  const clearGeneratingTitle = useCallback((chatId) => {
    if (!chatId) return
    setGeneratingTitleChatIds((prev) => {
      const next = new Set(prev)
      next.delete(chatId)
      return next
    })
  }, [])

  const persistTurn = useCallback(async (chatId, text, finalAnswer) => {
    try {
      await chatService.addMessage(chatId, 'User', text)
      await chatService.addMessage(chatId, 'Assistant', finalAnswer)
      chatService.processChatExit(chatId).catch(() => {})
      await refreshChatsAfterPersist(chatId)
    } catch (error) {
      console.error('Background persist error:', error)
      clearGeneratingTitle(chatId)
    }
  }, [clearGeneratingTitle, refreshChatsAfterPersist])

  const sendMessage = useCallback(async (text) => {
    const trimmed = text?.trim()
    if (!trimmed) return

    let chatId = currentChatId
    if (!chatId) {
      const createdChatId = await createNewChat()
      if (!createdChatId) return
      chatId = createdChatId
      setGeneratingTitleChatIds((prev) => new Set(prev).add(createdChatId))
    }

    const existingMessages = messagesRef.current
    const historyToSend = formatHistoryForPrompt(existingMessages)
    const mode = normalizeChatMode(answerMode)
    const turnId = createId('turn')
    const requestId = createId('request')
    const traceId = createId('trace')
    const timestamp = new Date().toISOString()
    const userMessageId = `user-${turnId}`
    const assistantMessageId = `assistant-${turnId}`

    const turn = {
      turnId,
      requestId,
      traceId,
      conversationId: chatId,
      mode,
      promptText: trimmed,
      historySent: historyToSend,
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
      startedAt: timestamp,
      userMessageId,
      assistantMessageId,
    }

    const userMessage = {
      id: userMessageId,
      turnId,
      sender: 'You',
      text: trimmed,
      timestamp,
      isLoading: false,
      metadata: {
        requestId,
        traceId,
        conversationId: chatId,
        turnId,
        historySent: historyToSend || null,
        mode,
      },
    }

    const assistantMessage = {
      id: assistantMessageId,
      turnId,
      sender: 'Assistant',
      text: '',
      timestamp: null,
      isLoading: true,
      metadata: buildAssistantMetadata(turn),
    }

    dispatchRuntime({
      type: 'TURN_STARTED',
      turn,
      userMessage,
      assistantMessage,
    })

    try {
      const doneEvent = await socketService.askQuestion(
        {
          question: trimmed,
          mode,
          model: selectedModel || defaultModel,
          conversation_id: chatId,
          request_id: requestId,
          turn_id: turnId,
          trace_id: traceId,
          history: historyToSend || undefined,
          debug: true,
        },
        {
          onStatus: (event) => dispatchRuntime({ type: 'TURN_STATUS', turnId, event }),
          onTrace: (event) => dispatchRuntime({ type: 'TURN_TRACE', turnId, event }),
          onToken: (event) => {
            const delta =
              event?.data?.text_delta ||
              event?.data?.token ||
              event?.data?.text ||
              ''
            if (delta) {
              dispatchRuntime({ type: 'TURN_TOKEN', turnId, delta })
            }
          },
          onAnswerReview: (event) => dispatchRuntime({ type: 'TURN_ANSWER_REVIEW', turnId, event }),
          onDone: (event) => dispatchRuntime({ type: 'TURN_DONE', turnId, event }),
          onError: (event) => dispatchRuntime({ type: 'TURN_ERROR', turnId, event }),
        }
      )

      const finalAnswer = doneEvent?.data?.final_answer || ''
      if (chatId && finalAnswer) {
        persistTurn(chatId, trimmed, finalAnswer)
      } else {
        clearGeneratingTitle(chatId)
      }
    } catch (error) {
      if (!error?.runtimeHandled) {
        dispatchRuntime({
          type: 'TURN_ERROR',
          turnId,
          event: error?.runtimeEvent || null,
          errorMessage: error?.message || 'Error sending message',
        })
      }
      clearGeneratingTitle(chatId)
    }
  }, [answerMode, clearGeneratingTitle, createNewChat, currentChatId, defaultModel, persistTurn, selectedModel])

  const sendFeedback = useCallback(async (turnId, feedbackType, payload = {}) => {
    const turn = runtimeState.turnsById[turnId]
    if (!turn) {
      throw new Error('Turn not found')
    }

    const feedbackKey = feedbackType === 'answer_feedback' ? 'answer' : 'flow'
    dispatchRuntime({
      type: 'TURN_FEEDBACK_STATE',
      turnId,
      feedbackKey,
      status: 'sending',
      payload,
    })

    try {
      await socketService.sendFeedback(feedbackType, {
        conversation_id: turn.conversationId,
        turn_id: turn.turnId,
        request_id: turn.requestId,
        trace_id: turn.traceId,
        mode: turn.mode,
        ...payload,
      })

      dispatchRuntime({
        type: 'TURN_FEEDBACK_STATE',
        turnId,
        feedbackKey,
        status: 'sent',
        payload,
      })
      return { sent: true }
    } catch (error) {
      dispatchRuntime({
        type: 'TURN_FEEDBACK_STATE',
        turnId,
        feedbackKey,
        status: 'error',
        error: error?.message || 'Failed to send feedback',
        payload,
      })
      throw error
    }
  }, [runtimeState.turnsById])

  const sendAnswerFeedback = useCallback((turnId, payload) => {
    return sendFeedback(turnId, 'answer_feedback', payload)
  }, [sendFeedback])

  const sendFlowFeedback = useCallback((turnId, payload) => {
    return sendFeedback(turnId, 'flow_feedback', payload)
  }, [sendFeedback])

  const deleteChat = useCallback(async (chatId) => {
    setDeletingChatIds((prev) => new Set(prev).add(chatId))
    try {
      await chatService.deleteChat(chatId)
      setChats((prev) => prev.filter((chat) => chat.id !== chatId))
      if (currentChatId === chatId) {
        dispatchRuntime({ type: 'RESET' })
        router.push('/')
      }
      dispatch(chatDeletedAction())
    } catch (error) {
      console.error('Delete chat error:', error)
    } finally {
      setDeletingChatIds((prev) => {
        const next = new Set(prev)
        next.delete(chatId)
        return next
      })
    }
  }, [currentChatId, dispatch, router])

  const activeTurn = runtimeState.activeTurnId ? runtimeState.turnsById[runtimeState.activeTurnId] : null
  const extendedProgress = useMemo(() => {
    if (!activeTurn || activeTurn.mode !== 'extended') return null
    return activeTurn.latestStatus
  }, [activeTurn])

  const value = useMemo(() => ({
    messages: runtimeState.messages,
    turnsById: runtimeState.turnsById,
    turnOrder: runtimeState.turnOrder,
    chatState: runtimeState.chatState,
    chats,
    currentChatId,
    loading,
    chatsLoading,
    chatsError,
    models,
    selectedModel,
    defaultModel,
    wsConnectionStatus,
    answerMode,
    sendingMessage: runtimeState.chatState === 'connecting' || runtimeState.chatState === 'streaming',
    deletingChatIds,
    generatingTitleChatIds,
    extendedProgress,
    selectChat,
    setSelectedModel,
    setAnswerMode,
    createNewChat,
    sendMessage,
    sendAnswerFeedback,
    sendFlowFeedback,
    deleteChat,
    loadChats,
  }), [
    runtimeState.messages,
    runtimeState.turnsById,
    runtimeState.turnOrder,
    runtimeState.chatState,
    chats,
    currentChatId,
    loading,
    chatsLoading,
    chatsError,
    models,
    selectedModel,
    defaultModel,
    wsConnectionStatus,
    answerMode,
    deletingChatIds,
    generatingTitleChatIds,
    extendedProgress,
    selectChat,
    setAnswerMode,
    createNewChat,
    sendMessage,
    sendAnswerFeedback,
    sendFlowFeedback,
    deleteChat,
    loadChats,
  ])

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

/** Read the shared chat runtime context. */
export function useChat() {
  const context = useContext(ChatContext)
  if (!context) {
    throw new Error('useChat must be used within ChatProvider')
  }
  return context
}
