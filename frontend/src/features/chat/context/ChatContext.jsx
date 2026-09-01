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
  useEffectEvent,
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
import {
  AUTO_TITLE_USER_MESSAGE_THRESHOLD,
  CHAT_MODE_STORAGE_KEY,
  initialConversationState,
  initialRuntimeState,
} from './chatConstants'
import {
  buildAssistantMetadata,
  createId,
  formatHistoryForPrompt,
  mapGatewayMessage,
  buildPersistedAssistantMetadata,
  buildPersistedUserMetadata,
  readReplyField,
} from './chatHelpers'
import { chatRuntimeReducer } from './chatReducers'

// Re-exported so existing importers (and the reducer test) keep their paths.
export { chatRuntimeReducer } from './chatReducers'
export { initialRuntimeState } from './chatConstants'

const ChatContext = createContext(null)


export function ChatProvider({ children }) {
  const pathname = usePathname()
  const router = useRouter()
  const dispatch = useDispatch()
  const [runtimeState, dispatchRuntime] = useReducer(chatRuntimeReducer, initialRuntimeState)
  const skipNextMessageLoadRef = useRef(null)
  const chatsRef = useRef([])
  const generatingTitleRef = useRef(new Set())
  // Chats that gained a completed turn since their last exit-processing — the
  // only ones worth curating/titling when the user leaves them.
  const dirtyChatIdsRef = useRef(new Set())
  const previousChatIdRef = useRef(null)

  const [chats, setChats] = useState([])
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

  // The URL is the single source of truth for which chat is open. Deriving it
  // during render, rather than mirroring it into state from an Effect, means a
  // navigation paints the new chat in one pass instead of two.
  const currentChatId = pathname?.match(/\/chat\/([^/]+)/)?.[1] || null

  // The visible chat is whichever conversation the URL points at. Everything the
  // UI reads (messages, turns, chatState) is derived from that one bucket.
  const activeConversation = runtimeState.conversations[currentChatId] || initialConversationState

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

  // Reads the *current* conversation buckets without making them a dependency of
  // the Effect below, which must fire on navigation only — never when a
  // streaming turn mutates the bucket it is already displaying.
  const loadMessagesIfUnseen = useEffectEvent((chatId) => {
    // A conversation already has a bucket once it has been loaded or has streamed
    // this session — reusing it preserves an in-flight answer and skips a refetch.
    if (runtimeState.conversations[chatId]) return
    loadMessages(chatId)
  })

  useEffect(() => {
    if (!currentChatId) return

    if (skipNextMessageLoadRef.current === currentChatId) {
      skipNextMessageLoadRef.current = null
      return
    }

    loadMessagesIfUnseen(currentChatId)
  }, [currentChatId])

  const loadModels = useCallback(async () => {
    try {
      const data = await chatService.getModels()
      const modelList = data.models || data.data?.models || []
      if (Array.isArray(modelList) && modelList.length > 0) {
        setModels(modelList)
        // Seed the default through a functional update rather than reading
        // `selectedModel`. Depending on it made this callback — and therefore
        // the Effect below — re-run, refetching /models every time the user
        // picked a different model.
        const first = modelList[0]
        const name = typeof first === 'object' ? first?.name : first
        if (name) setSelectedModel((current) => current || name)
        return
      }
      setModels([])
    } catch (_) {
      setModels([])
    }
  }, [])

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

  // Manual rename. The sidebar shows the new title immediately and restores the
  // previous one if the gateway rejects it, so a failed rename never leaves the
  // list disagreeing with the server.
  const renameChat = useCallback(async (chatId, title) => {
    const nextTitle = title?.trim()
    if (!chatId || !nextTitle) return
    const previousTitle = chatsRef.current.find((chat) => chat.id === chatId)?.title
    setChats((prev) => prev.map((chat) => (chat.id === chatId ? { ...chat, title: nextTitle } : chat)))
    try {
      await chatService.updateChatTitle(chatId, nextTitle)
    } catch (error) {
      console.error('Rename chat error:', error)
      if (previousTitle != null) {
        setChats((prev) => prev.map((chat) => (chat.id === chatId ? { ...chat, title: previousTitle } : chat)))
      }
    }
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

  const persistTurn = useCallback(async (chatId, text, finalAnswer, turn, doneEvent) => {
    try {
      await chatService.addMessage(chatId, 'User', text, buildPersistedUserMetadata(turn))
      await chatService.addMessage(
        chatId,
        'Assistant',
        finalAnswer,
        buildPersistedAssistantMetadata(turn, doneEvent)
      )
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

    const existingMessages = activeConversation.messages
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
        persistTurn(chatId, trimmed, finalAnswer, turn, doneEvent)
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
  }, [activeConversation.messages, answerMode, createNewChat, currentChatId, defaultModel, maybeAutoTitle, persistTurn, selectedModel])

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
  // The RAG graph emits a `status` event with the real node name for every
  // mode, so the live stage is shown for quick answers too — not only for deep
  // research. A plain property read: memoising it bought a cache slot and a
  // dependency check per render and nothing else.
  const activityStatus = activeTurn ? activeTurn.latestStatus : null

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
    activityStatus,
    selectChat,
    setSelectedModel,
    setAnswerMode,
    createNewChat,
    sendMessage,
    sendAnswerFeedback,
    sendFlowFeedback,
    renameChat,
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
    activityStatus,
    selectChat,
    setAnswerMode,
    createNewChat,
    sendMessage,
    sendAnswerFeedback,
    sendFlowFeedback,
    renameChat,
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
