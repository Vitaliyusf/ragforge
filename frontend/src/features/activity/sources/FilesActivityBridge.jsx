'use client'

/**
 * File activity, derived from the file list the app already keeps.
 *
 * The Files tab polls every 5s while it is open and writes each result into
 * the store; this bridge reads that store, so an open Files tab costs no
 * extra requests at all. It falls back to a slower poll only when work is
 * known to be in flight and no Files surface is mounted to keep the list
 * fresh — never while everything is idle.
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import fileService from '@/features/files/services/fileService'
import { selectCachedFiles, setFiles } from '@/store/slices/filesSlice'
import { computeEffectiveStatus } from '@/features/files/fileStatus'
import {
  ACTIVITY_FEATURES,
  ACTIVITY_STATES,
  FILE_ACTIVE_STATUSES,
  FILE_FAILED_STATUSES,
  IDLE_ACTIVITY,
} from '../activityModel'
import { useActivity } from '../ActivityContext'

/** Slower than the Files tab's own 5s, and only while files are processing. */
export const NAV_FILES_POLL_INTERVAL = 10000

const fileId = (file) => file?.file_id || file?.id || file?.filename

/** Which of the known files are working, and which of them ended badly. */
export function summarizeFiles(files) {
  const active = []
  const statusById = new Map()
  for (const file of files || []) {
    const status = computeEffectiveStatus(file)
    const id = fileId(file)
    if (id) statusById.set(id, status)
    if (FILE_ACTIVE_STATUSES.has(status)) active.push(id)
  }
  return { activeIds: active, statusById }
}

/** The state a batch of finished files lands in. Failure outranks review. */
export function settleFiles(watchedIds, statusById) {
  let failed = 0
  let review = 0
  for (const id of watchedIds) {
    const status = statusById.get(id)
    if (FILE_FAILED_STATUSES.has(status)) failed += 1
    else if (status === 'awaiting_review') review += 1
  }
  if (failed) {
    return {
      state: ACTIVITY_STATES.FAILED,
      count: failed,
      message: failed === 1 ? '1 file failed' : `${failed} files failed`,
    }
  }
  if (review) {
    return {
      state: ACTIVITY_STATES.WARNING,
      count: review,
      message: review === 1 ? '1 file needs review' : `${review} files need review`,
    }
  }
  return { state: ACTIVITY_STATES.SUCCESS, count: watchedIds.length || undefined }
}

export default function FilesActivityBridge({ enabled = true }) {
  const dispatch = useDispatch()
  const files = useSelector(selectCachedFiles)
  const { publish, hasLiveSource, liveVersion } = useActivity()
  const [entry, setEntry] = useState(IDLE_ACTIVITY)
  const watchedRef = useRef([])
  const startedAtRef = useRef(null)

  const { activeIds, statusById } = useMemo(() => summarizeFiles(files), [files])
  const statusRef = useRef(statusById)
  statusRef.current = statusById
  const activeCount = activeIds.length
  // The poll rebuilds the list object every few seconds. Keying the effect on
  // which files are working — not on the array identity — keeps a steady
  // "processing 2 files" from re-publishing on every tick.
  const activeSignature = activeIds.join('|')

  useEffect(() => {
    if (!enabled) return
    if (activeCount > 0) {
      watchedRef.current = activeIds
      if (!startedAtRef.current) startedAtRef.current = new Date().toISOString()
      setEntry({
        state: ACTIVITY_STATES.RUNNING,
        count: activeCount,
        message: activeCount === 1 ? 'processing 1 file' : `processing ${activeCount} files`,
        startedAt: startedAtRef.current,
      })
      return
    }
    startedAtRef.current = null
    if (!watchedRef.current.length) return
    const watched = watchedRef.current
    watchedRef.current = []
    setEntry({ ...settleFiles(watched, statusRef.current), completedAt: new Date().toISOString() })
  }, [enabled, activeCount, activeSignature])

  useEffect(() => {
    if (!enabled) return
    publish(ACTIVITY_FEATURES.FILES, entry)
  }, [enabled, entry, publish])

  const pageOwnsPolling = hasLiveSource(ACTIVITY_FEATURES.FILES)
  useEffect(() => {
    if (!enabled || activeCount === 0 || pageOwnsPolling) return undefined
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return undefined
    let cancelled = false
    const poll = async () => {
      try {
        const data = await fileService.getFiles()
        if (!cancelled && data?.files) dispatch(setFiles(data.files))
      } catch {
        // The next tick retries; a failed refresh is not a failed file.
      }
    }
    const timer = setInterval(poll, NAV_FILES_POLL_INTERVAL)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [enabled, activeCount, pageOwnsPolling, liveVersion, dispatch])

  return null
}
