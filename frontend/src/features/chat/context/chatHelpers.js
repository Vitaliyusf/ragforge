/** Pure helpers for shaping chat messages and turn metadata. */

import { HISTORY_MESSAGE_LIMIT } from './chatConstants'

const MAX_METADATA_DEPTH = 5
const MAX_METADATA_ITEMS = 40
const MAX_METADATA_STRING = 4000
const PRIVATE_METADATA_KEY = /(auth|credential|password|secret|session|token)/i
const SOURCE_KEYS = [
  'file_id', 'document_id', 'chunk_id', 'chunk_index', 'chunk_version',
  'source_name', 'source', 'filename', 'title', 'page', 'score', 'similarity',
  'retrieval_allowed', 'review_status', 'issue_flags', 'created_at',
]
const DEBUG_KEYS = new Set([
  'generation_instructions', 'rewrite_response', 'system_prompt', 'raw_prompt',
  'visible_reasoning_summary', 'visible_reasoning_steps', 'input_safety_flags',
  'raw_input_safety_flags', 'output_safety_flags', 'raw_output_safety_flags',
  'raw_output', 'output_safety_structured_output_candidates',
  'output_safety_structured_output_selected_index',
  'output_safety_structured_output_selection_policy',
  'output_safety_structured_output_extraction_mode', 'output_safety_raw_output',
])

function boundedJson(value, depth = 0) {
  if (value == null || typeof value === 'boolean' || typeof value === 'number') return value
  if (typeof value === 'string') return value.slice(0, MAX_METADATA_STRING)
  if (depth >= MAX_METADATA_DEPTH) return null
  if (Array.isArray(value)) {
    return value.slice(0, MAX_METADATA_ITEMS).map((item) => boundedJson(item, depth + 1))
  }
  if (typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => !PRIVATE_METADATA_KEY.test(key))
        .slice(0, MAX_METADATA_ITEMS)
        .map(([key, item]) => [key, boundedJson(item, depth + 1)])
    )
  }
  return null
}

function sanitizeSources(sources) {
  if (!Array.isArray(sources)) return []
  return sources.slice(0, MAX_METADATA_ITEMS).map((source) => {
    const safe = {}
    for (const key of SOURCE_KEYS) {
      if (source?.[key] != null) safe[key] = boundedJson(source[key])
    }
    // Persist only the already-bounded preview, never the raw private chunk.
    if (typeof source?.text_preview === 'string') {
      safe.text_preview = source.text_preview.slice(0, 500)
    }
    return safe
  })
}

function sanitizeDebugPayloads(payloads) {
  if (!payloads || typeof payloads !== 'object' || Array.isArray(payloads)) return {}
  return Object.fromEntries(
    Object.entries(payloads)
      .filter(([key]) => DEBUG_KEYS.has(key) && !PRIVATE_METADATA_KEY.test(key))
      .map(([key, value]) => [key, boundedJson(value)])
  )
}

/** Durable metadata for a completed assistant turn, sourced only from TURN_DONE. */
export function buildPersistedAssistantMetadata(turn, doneEvent) {
  const data = doneEvent?.data || {}
  return {
    requestId: doneEvent?.request_id || turn.requestId,
    traceId: doneEvent?.trace_id || turn.traceId,
    conversationId: doneEvent?.conversation_id || turn.conversationId,
    turnId: doneEvent?.turn_id || turn.turnId,
    mode: turn.mode,
    answerReview: boundedJson(data.review_summary || turn.answerReview || null),
    sources: sanitizeSources(data.sources || turn.sources),
    retrievalSummary: boundedJson(data.retrieval_summary || turn.retrievalSummary || null),
    traceEvents: boundedJson(data.trace_summary || turn.traceEvents || []),
    // Only the server-redacted payload is durable. Never fall back to debug_payloads.
    debugPayloads: sanitizeDebugPayloads(data.safe_debug_payloads),
  }
}

export function buildPersistedUserMetadata(turn) {
  return {
    requestId: turn.requestId,
    traceId: turn.traceId,
    conversationId: turn.conversationId,
    turnId: turn.turnId,
    mode: turn.mode,
  }
}

export function createId(prefix) {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`
}

export function formatHistoryForPrompt(messages) {
  if (!messages?.length) return ''
  const recent = messages
    .filter((message) => (message.text || '').trim().length > 0)
    .slice(-HISTORY_MESSAGE_LIMIT)
  return recent.map((message) => `[${message.sender}]: ${message.text || ''}`).join('\n')
}

// RPC replies reach the browser either flat or nested under `data`/`payload`;
// read a field from whichever shape it arrives in.
export function readReplyField(data, key) {
  return data?.[key] || data?.data?.[key] || data?.payload?.[key] || null
}

export function mapGatewayMessage(message) {
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

export function buildAssistantMetadata(turn) {
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
