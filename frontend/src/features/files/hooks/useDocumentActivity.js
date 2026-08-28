'use client'

/**
 * The audit trail behind one document's Activity section.
 *
 * This is the only per-document request the Documents screen makes, and it is
 * made once, when a drawer opens. Rows never fetch: everything a row shows
 * already arrived with the list.
 */

import { useCallback, useRef, useState } from 'react'
import fileService from '@/features/files/services/fileService'

const EMPTY = {
  events: [],
  nextCursor: null,
  loading: false,
  loadingMore: false,
  error: null,
}

export function useDocumentActivity() {
  const [activity, setActivity] = useState(EMPTY)
  // Which document the in-flight page belongs to, so a fast drawer switch
  // cannot land the previous document's events in the current one.
  const activeIdRef = useRef(null)
  // The pagination cursor and in-flight flag are mirrored in refs so
  // `loadMoreActivity` can read them without a state updater doing the
  // reading — a state updater must stay pure.
  const cursorRef = useRef(null)
  const loadingMoreRef = useRef(false)

  const loadActivity = useCallback(async (fileId) => {
    activeIdRef.current = fileId
    cursorRef.current = null
    loadingMoreRef.current = false
    setActivity({ ...EMPTY, loading: true })
    try {
      const response = await fileService.getAuditTrail(fileId)
      if (activeIdRef.current !== fileId) return
      cursorRef.current = response?.next_cursor || null
      setActivity({
        ...EMPTY,
        events: Array.isArray(response?.events) ? response.events : [],
        nextCursor: cursorRef.current,
      })
    } catch (error) {
      if (activeIdRef.current !== fileId) return
      setActivity({ ...EMPTY, error: error?.message || 'Could not load the activity trail.' })
    }
  }, [])

  const loadMoreActivity = useCallback(async (fileId) => {
    const cursor = cursorRef.current
    if (!cursor || loadingMoreRef.current) return
    loadingMoreRef.current = true
    setActivity((current) => ({ ...current, loadingMore: true, error: null }))

    try {
      const response = await fileService.getAuditTrail(fileId, { cursor })
      loadingMoreRef.current = false
      if (activeIdRef.current !== fileId) return
      cursorRef.current = response?.next_cursor || null
      setActivity((current) => ({
        ...current,
        events: [...current.events, ...(Array.isArray(response?.events) ? response.events : [])],
        nextCursor: cursorRef.current,
        loadingMore: false,
      }))
    } catch (error) {
      loadingMoreRef.current = false
      if (activeIdRef.current !== fileId) return
      setActivity((current) => ({
        ...current,
        loadingMore: false,
        error: error?.message || 'Could not load more activity.',
      }))
    }
  }, [])

  const resetActivity = useCallback(() => {
    activeIdRef.current = null
    cursorRef.current = null
    loadingMoreRef.current = false
    setActivity(EMPTY)
  }, [])

  return { activity, loadActivity, loadMoreActivity, resetActivity }
}
