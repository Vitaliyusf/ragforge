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
// Auto-title a still-"New Chat" conversation as soon as the first LLM reply
// arrives (i.e. after the user's first message); leaving the chat re-titles as
// a fallback via process-exit.
const AUTO_TITLE_USER_MESSAGE_THRESHOLD = 1

// Runtime state for a single conversation. Turns and their streamed messages
// live here so that switching the visible chat never disturbs another chat's
// in-flight answer.
const initialConversationState = {
  messages: [],
  turnsById: {},
  turnOrder: [],
  chatState: 'idle',
  activeTurnId: null,
}

// Top-level runtime state: a map of conversation id -> conversation bucket. The
// visible chat is derived from the URL-driven currentChatId, not stored here.
export const initialRuntimeState = {
  conversations: {},
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

// RPC replies reach the browser either flat or nested under `data`/`payload`;
// read a field from whichever shape it arrives in.
function readReplyField(data, key) {
  return data?.[key] || data?.data?.[key] || data?.payload?.[key] || null
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

// Reducer for a single conversation bucket. Every case operates purely on that
// bucket's { messages, turnsById, ... } — it never reaches across conversations.
function conversationReducer(state, action) {
  switch (action.type) {
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

// Top-level reducer: routes each action to its conversation's bucket by
// `conversationId`, so a turn can only ever mutate the chat that owns it.
export function chatRuntimeReducer(state, action) {
  switch (action.type) {
    case 'HISTORY_LOADED': {
      // Never overwrite a bucket that is mid-stream — a late history fetch for a
      // chat you returned to must not wipe its in-flight answer.
      const existing = state.conversations[action.conversationId]
      if (existing && existing.activeTurnId) return state
      return {
        ...state,
        conversations: {
          ...state.conversations,
          [action.conversationId]: { ...initialConversationState, messages: action.messages },
        },
      }
    }

    case 'REMOVE_CONVERSATION': {
      if (!state.conversations[action.conversationId]) return state
      const nextConversations = { ...state.conversations }
      delete nextConversations[action.conversationId]
      return { ...state, conversations: nextConversations }
    }

    default: {
      const { conversationId } = action
      if (!conversationId) return state
      const current = state.conversations[conversationId] || initialConversationState
      const updated = conversationReducer(current, action)
      if (updated === current) return state
      return {
        ...state,
        conversations: { ...state.conversations, [conversationId]: updated },
      }
    }
  }
}

export function ChatProvider({ children }) {
  const pathname = usePathname()
  const router = useRouter()
  const dispatch = useDispatch()
  const [runtimeState, dispatchRuntime] = useReducer(chatRuntimeReducer, initialRuntimeState)
  const messagesRef = useRef(initialConversationState.messages)
  const conversationsRef = useRef(runtimeState.conversations)
  const skipNextMessageLoadRef = useRef(null)
  const chatsRef = useRef([])
  const generatingTitleRef = useRef(new Set())
  // Chats that gained a completed turn since their last exit-processing — the
  // only ones worth curating/titling when the user leaves them.
  const dirtyChatIdsRef = useRef(new Set())
  const previousChatIdRef = useRef(null)

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

  // The visible chat is whichever conversation the URL points at. Everything the
  // UI reads (messages, turns, chatState) is derived from that one bucket.
  const activeConversation = runtimeState.conversations[currentChatId] || initialConversationState

  useEffect(() => {
    messagesRef.current = activeConversation.messages
  }, [activeConversation.messages])

  useEffect(() => {
    conversationsRef.current = runtimeState.conversations
  }, [runtimeState.conversations])

  useEffect(() => {
    chatsRef.current = chats
  }, [chats])

  useEffect(() => {
    generatingTitleRef.current = generatingTitleChatIds
  }, [generatingTitleChatIds])

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

  const loadMessages = useCallback(async (chatId, isRetry = false) => {
    if (!chatId) return

    setLoading(true)
    try {
      const data = await chatService.getMessages(chatId)
      const messageList = data.messages || data.data?.messages || []
      const formatted = (Array.isArray(messageList) ? messageList : []).map(mapGatewayMessage)
      dispatchRuntime({ type: 'HISTORY_LOADED', conversationId: chatId, messages: formatted })
      setChatsError(null)
    } catch (error) {
      const isTransient =
        error?.status === 504 ||
        error?.statusCode === 504 ||
        error?.type === 'timeout' ||
        (typeof error?.message === 'string' &&
          (error.message.includes('504') ||
            error.message.toLowerCase().includes('timeout') ||
            error.message.toLowerCase().includes('gateway timeout')))
      // A slow memory service can briefly stall history; retry once before giving up.
      if (isTransient && !isRetry) {
        setLoading(false)
        await new Promise((resolve) => setTimeout(resolve, 2500))
        return loadMessages(chatId, true)
      }
      // Crucially, do NOT seed an empty bucket on failure: leaving the chat
      // unloaded lets a later visit retry instead of showing a permanently
      // blank thread (the message-load effect skips chats that already have a
      // bucket).
      setChatsError('Chat history is unavailable. Please ensure the gateway and memory services are running.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadChats()
  }, [loadChats])

  useEffect(() => {
    const chatIdFromPath = pathname?.match(/\/chat\/([^/]+)/)?.[1]
    setCurrentChatId(chatIdFromPath || null)
  }, [pathname])

  useEffect(() => {
    if (!currentChatId) return

    if (skipNextMessageLoadRef.current === currentChatId) {
      skipNextMessageLoadRef.current = null
      return
    }

    // A conversation already has a bucket once it has been loaded or has streamed
    // this session — reusing it preserves an in-flight answer and skips a refetch.
    if (conversationsRef.current[currentChatId]) return

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
      // Seed an empty bucket so the new chat renders immediately, and skip the
      // message reload the pathname effect would otherwise trigger for it.
      skipNextMessageLoadRef.current = chatId
      dispatchRuntime({ type: 'HISTORY_LOADED', conversationId: chatId, messages: [] })
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

  // Write a resolved title straight into the sidebar; never downgrade a real
  // title back to the "New Chat" placeholder.
  const applyTitle = useCallback((chatId, title) => {
    if (!chatId || !title || title === 'New Chat') return
    setChats((prev) => prev.map((chat) => (
      chat.id === chatId ? { ...chat, title } : chat
    )))
  }, [])

  // Trigger A — name a still-untitled chat from its transcript once it is
  // substantial enough. The backend is idempotent; the local guards just avoid
  // redundant calls on chats that are already named or in flight.
  const maybeAutoTitle = useCallback(async (chatId) => {
    if (!chatId) return
    const chat = chatsRef.current.find((item) => item.id === chatId)
    if (chat && chat.title !== 'New Chat') return
    if (generatingTitleRef.current.has(chatId)) return

    setGeneratingTitleChatIds((prev) => new Set(prev).add(chatId))
    try {
      const data = await chatService.generateTitle(chatId)
      applyTitle(chatId, readReplyField(data, 'title'))
    } catch (error) {
      console.error('Auto-title error:', error)
    } finally {
      setGeneratingTitleChatIds((prev) => {
        const next = new Set(prev)
        next.delete(chatId)
        return next
      })
    }
  }, [applyTitle])

  // Trigger B — when the user leaves a chat they actually used, curate memory,
  // store a summary, and title it if still unnamed (all via process-exit).
  const processChatExitOnLeave = useCallback((chatId) => {
    if (!chatId || !dirtyChatIdsRef.current.has(chatId)) return
    dirtyChatIdsRef.current.delete(chatId)
    chatService.processChatExit(chatId)
      .then((data) => applyTitle(chatId, readReplyField(data, 'headline')))
      .catch(() => {})
  }, [applyTitle])

  const persistTurn = useCallback(async (chatId, text, finalAnswer) => {
    try {
      await chatService.addMessage(chatId, 'User', text)
      await chatService.addMessage(chatId, 'Assistant', finalAnswer)
      setChats((prev) => prev.map((chat) => (
        chat.id === chatId ? { ...chat, updated_at: new Date().toISOString() } : chat
      )))
    } catch (error) {
      console.error('Background persist error:', error)
    }
  }, [])

  // Leaving a chat = the active chat changes (navigation) — curate + title the
  // one we just left. Tracked via a ref so this fires exactly on the transition.
  useEffect(() => {
    const previous = previousChatIdRef.current
    if (previous && previous !== currentChatId) {
      processChatExitOnLeave(previous)
    }
    previousChatIdRef.current = currentChatId
  }, [currentChatId, processChatExitOnLeave])

  // Best-effort: leaving the browser tab is also "leaving the chat".
  useEffect(() => {
    if (typeof document === 'undefined') return undefined
    const handleHidden = () => {
      if (document.visibilityState === 'hidden') {
        processChatExitOnLeave(previousChatIdRef.current)
      }
    }
    document.addEventListener('visibilitychange', handleHidden)
    return () => document.removeEventListener('visibilitychange', handleHidden)
  }, [processChatExitOnLeave])

  const sendMessage = useCallback(async (text) => {
    const trimmed = text?.trim()
    if (!trimmed) return

    let chatId = currentChatId
    if (!chatId) {
      const createdChatId = await createNewChat()
      if (!createdChatId) return
      chatId = createdChatId
    }

    const existingMessages = messagesRef.current
    // Runtime messages are tagged "You"; history reloaded from the server uses
    // "User" — count both so a reopened chat still titles on the 3rd message.
    const userMessageCount = existingMessages.filter(
      (message) => message.sender === 'You' || message.sender === 'User'
    ).length + 1
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
      conversationId: chatId,
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
          onStatus: (event) => dispatchRuntime({ type: 'TURN_STATUS', conversationId: chatId, turnId, event }),
          onTrace: (event) => dispatchRuntime({ type: 'TURN_TRACE', conversationId: chatId, turnId, event }),
          onToken: (event) => {
            const delta =
              event?.data?.text_delta ||
              event?.data?.token ||
              event?.data?.text ||
              ''
            if (delta) {
              dispatchRuntime({ type: 'TURN_TOKEN', conversationId: chatId, turnId, delta })
            }
          },
          onAnswerReview: (event) => dispatchRuntime({ type: 'TURN_ANSWER_REVIEW', conversationId: chatId, turnId, event }),
          onDone: (event) => dispatchRuntime({ type: 'TURN_DONE', conversationId: chatId, turnId, event }),
          onError: (event) => dispatchRuntime({ type: 'TURN_ERROR', conversationId: chatId, turnId, event }),
        }
      )

      const finalAnswer = doneEvent?.data?.final_answer || ''
      if (chatId && finalAnswer) {
        // The chat now has a completed turn worth curating when the user leaves.
        dirtyChatIdsRef.current.add(chatId)
        persistTurn(chatId, trimmed, finalAnswer)
        if (userMessageCount >= AUTO_TITLE_USER_MESSAGE_THRESHOLD) {
          maybeAutoTitle(chatId)
        }
      }
    } catch (error) {
      if (!error?.runtimeHandled) {
        dispatchRuntime({
          type: 'TURN_ERROR',
          conversationId: chatId,
          turnId,
          event: error?.runtimeEvent || null,
          errorMessage: error?.message || 'Error sending message',
        })
      }
    }
  }, [answerMode, createNewChat, currentChatId, defaultModel, maybeAutoTitle, persistTurn, selectedModel])

  const sendFeedback = useCallback(async (turnId, feedbackType, payload = {}) => {
    const turn = activeConversation.turnsById[turnId]
    if (!turn) {
      throw new Error('Turn not found')
    }

    const conversationId = turn.conversationId
    const feedbackKey = feedbackType === 'answer_feedback' ? 'answer' : 'flow'
    dispatchRuntime({
      type: 'TURN_FEEDBACK_STATE',
      conversationId,
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
        conversationId,
        turnId,
        feedbackKey,
        status: 'sent',
        payload,
      })
      return { sent: true }
    } catch (error) {
      dispatchRuntime({
        type: 'TURN_FEEDBACK_STATE',
        conversationId,
        turnId,
        feedbackKey,
        status: 'error',
        error: error?.message || 'Failed to send feedback',
        payload,
      })
      throw error
    }
  }, [activeConversation.turnsById])

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
      dirtyChatIdsRef.current.delete(chatId)
      setChats((prev) => prev.filter((chat) => chat.id !== chatId))
      dispatchRuntime({ type: 'REMOVE_CONVERSATION', conversationId: chatId })
      if (currentChatId === chatId) {
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

  const activeTurn = activeConversation.activeTurnId
    ? activeConversation.turnsById[activeConversation.activeTurnId]
    : null
  const extendedProgress = useMemo(() => {
    if (!activeTurn || activeTurn.mode !== 'extended') return null
    return activeTurn.latestStatus
  }, [activeTurn])

  const value = useMemo(() => ({
    messages: activeConversation.messages,
    turnsById: activeConversation.turnsById,
    turnOrder: activeConversation.turnOrder,
    chatState: activeConversation.chatState,
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
    sendingMessage: activeConversation.chatState === 'connecting' || activeConversation.chatState === 'streaming',
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
    activeConversation.messages,
    activeConversation.turnsById,
    activeConversation.turnOrder,
    activeConversation.chatState,
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
