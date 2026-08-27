'use client'

/**
 * Chat activity, derived from the streaming lifecycle that already exists.
 *
 * Nothing is polled and the streaming protocol is untouched: this watches
 * the conversation state the chat runtime already publishes and turns the
 * transitions — not the resting values — into activity. Re-opening a
 * conversation that finished an hour ago must not flash a success dot.
 */

import { useEffect, useRef, useState } from 'react'
import { useChat } from '@/features/chat/context/ChatContext'
import { ACTIVITY_FEATURES, ACTIVITY_STATES, IDLE_ACTIVITY, mapChatState } from '../activityModel'
import { useActivity } from '../ActivityContext'

/**
 * Chat finishes many times an hour. A success dot that waited to be visited
 * would be permanently lit, so it clears itself; only failure waits.
 */
export const CHAT_SUCCESS_TTL = 2500

export default function ChatActivityBridge() {
  const { chatState } = useChat()
  const { publish } = useActivity()
  const [entry, setEntry] = useState(IDLE_ACTIVITY)
  const wasRunningRef = useRef(false)

  useEffect(() => {
    const state = mapChatState(chatState)
    if (state === ACTIVITY_STATES.RUNNING) {
      wasRunningRef.current = true
      setEntry({ state, startedAt: new Date().toISOString() })
      return undefined
    }
    // A terminal chat state only means something if this bridge saw the
    // request start. Switching to an already-finished conversation does not.
    if (!wasRunningRef.current) return undefined
    wasRunningRef.current = false
    if (state === ACTIVITY_STATES.SUCCESS) {
      setEntry({ state, completedAt: new Date().toISOString() })
      const timer = setTimeout(() => setEntry(IDLE_ACTIVITY), CHAT_SUCCESS_TTL)
      return () => clearTimeout(timer)
    }
    if (state === ACTIVITY_STATES.FAILED) {
      setEntry({ state, completedAt: new Date().toISOString() })
    }
    return undefined
  }, [chatState])

  useEffect(() => {
    publish(ACTIVITY_FEATURES.CHAT, entry)
  }, [entry, publish])

  return null
}
