/** Shared constants and initial state for the chat runtime. */

export const HISTORY_MESSAGE_LIMIT = 10
export const CHAT_MODE_STORAGE_KEY = 'ragforge-chat-mode'
// Auto-title a still-"New Chat" conversation as soon as the first LLM reply
// arrives (i.e. after the user's first message); leaving the chat re-titles as
// a fallback via process-exit.
export const AUTO_TITLE_USER_MESSAGE_THRESHOLD = 1

// Runtime state for a single conversation. Turns and their streamed messages
// live here so that switching the visible chat never disturbs another chat's
// in-flight answer.
export const initialConversationState = {
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
