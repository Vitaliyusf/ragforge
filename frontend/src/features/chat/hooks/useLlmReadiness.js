/** Poll the LLM readiness probe so the chat can gate its composer until vLLM is up. */
import { useState, useEffect, useRef, useCallback } from 'react'
import llmStatusService from '../services/llmStatusService'

const POLL_INTERVAL = 10000

/**
 * Tracks whether the LLM backend is ready to answer.
 *
 * - `llmReady`  — true only once the backend confirms vLLM is available.
 * - `llmChecked` — false until the first probe resolves, so the UI can show a
 *   neutral "starting" state instead of "unavailable" on initial load.
 *
 * Any failure (transport, auth, backend not up yet) is treated as "not ready".
 */
export function useLlmReadiness() {
  const [llmReady, setLlmReady] = useState(false)
  const [llmChecked, setLlmChecked] = useState(false)
  const intervalRef = useRef(null)

  const check = useCallback(async () => {
    try {
      const data = await llmStatusService.getReadiness()
      setLlmReady(Boolean(data?.ready))
    } catch (_) {
      setLlmReady(false)
    } finally {
      setLlmChecked(true)
    }
  }, [])

  useEffect(() => {
    check()
    intervalRef.current = setInterval(check, POLL_INTERVAL)
    return () => clearInterval(intervalRef.current)
  }, [check])

  return { llmReady, llmChecked }
}
