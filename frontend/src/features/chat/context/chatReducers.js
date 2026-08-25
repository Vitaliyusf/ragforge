/**
 * Conversation and runtime reducers.
 *
 * chatRuntimeReducer keys every turn by conversation id, which is what stops
 * a turn belonging to one chat from mutating another chat's window.
 */

import { initialConversationState, initialRuntimeState } from './chatConstants'
import { buildAssistantMetadata } from './chatHelpers'

export function updateMessage(messages, messageId, updater) {
  return messages.map((message) => {
    if (message.id !== messageId) return message
    const next = typeof updater === 'function' ? updater(message) : updater
    return { ...message, ...next }
  })
}

export function updateTurn(state, turnId, updater, nextChatState = state.chatState) {
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
export function conversationReducer(state, action) {
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
