/** Pure helpers for shaping chat messages and turn metadata. */

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
