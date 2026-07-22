'use client'

/**
 * Gateway-backed file state hook for upload, review, summary, and re-ingestion UI.
 *
 * Local reducer state tracks optimistic UI transitions. On every successful fetch
 * the file list is also written into Redux (filesSlice) so the Files tab can render
 * cached data immediately on first mount while the background poll is in flight.
 */

import { useCallback, useEffect, useReducer, useRef } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { filesChanged } from '@/store/slices/eventsSlice'
import { setFiles, selectCachedFiles } from '@/store/slices/filesSlice'
import fileService from '@/features/files/services/fileService'
import { normalizeFileStatus } from '@/utils/common'

function normalizeFileRecord(file) {
  if (!file) return file
  return {
    ...file,
    document_id: file.document_id || file.file_id,
  }
}

function deriveReviewState(file, existingState) {
  if (existingState === 'decision submitting') {
    return existingState
  }

  const status = normalizeFileStatus(file?.status)
  if (status === 'awaiting_review' || file?.review_status === 'pending') {
    return 'awaiting review'
  }
  if (status === 'rejected' || file?.review_status === 'rejected') {
    return 'rejected'
  }
  if (file?.latest_review_case_id && ['approved_sanitized', 'approved_as_is'].includes(file?.review_status)) {
    return 'resumed'
  }
  return 'no review'
}

function upsertFile(files, nextFile) {
  const normalizedFile = normalizeFileRecord(nextFile)
  const fileIndex = files.findIndex((file) => file.file_id === normalizedFile.file_id)
  if (fileIndex === -1) {
    return [normalizedFile, ...files]
  }

  const copy = [...files]
  copy[fileIndex] = { ...copy[fileIndex], ...normalizedFile }
  return copy
}

function buildInitialState(cachedFiles) {
  return {
    files: cachedFiles.map(normalizeFileRecord),
    loading: false,
    uploading: false,
    deletingFileIds: new Set(),
    reingestingFileIds: new Set(),
    recentUploads: [],
    reviewStatesByFileId: {},
    reviewCasesByFileId: {},
    reviewErrorsByFileId: {},
    summaryByFileId: {},
    summaryLoadingFileIds: new Set(),
    activeSummaryFileId: null,
    activeReviewFileId: null,
  }
}

function filesReducer(state, action) {
  switch (action.type) {
    case 'LOAD_START':
      return { ...state, loading: true }

    case 'LOAD_SUCCESS': {
      const nextReviewStates = { ...state.reviewStatesByFileId }
      const normalizedFiles = action.files.map(normalizeFileRecord)

      normalizedFiles.forEach((file) => {
        nextReviewStates[file.file_id] = deriveReviewState(file, nextReviewStates[file.file_id])
      })

      return {
        ...state,
        loading: false,
        files: normalizedFiles,
        reviewStatesByFileId: nextReviewStates,
      }
    }

    case 'LOAD_ERROR':
      return { ...state, loading: false }

    case 'UPLOAD_START':
      return { ...state, uploading: true }

    case 'UPLOAD_RESPONSE': {
      const optimisticFile = {
        file_id: action.response.file_id,
        document_id: action.response.document_id || action.response.file_id,
        current_task_id: action.response.current_task_id || action.response.task_id,
        filename: action.response.filename || action.file.name,
        size: action.file.size,
        content_type: action.file.type,
        status: action.response.status || 'started',
        message: action.response.message,
        request_id: action.response.request_id,
        trace_id: action.response.trace_id,
      }

      return {
        ...state,
        files: upsertFile(state.files, optimisticFile),
        recentUploads: [
          {
            ...optimisticFile,
            uploadedAt: new Date().toISOString(),
          },
          ...state.recentUploads,
        ].slice(0, 6),
        reviewStatesByFileId: {
          ...state.reviewStatesByFileId,
          [optimisticFile.file_id]: deriveReviewState(optimisticFile),
        },
      }
    }

    case 'UPLOAD_COMPLETE':
      return { ...state, uploading: false }

    case 'DELETE_START': {
      const nextDeleting = new Set(state.deletingFileIds)
      nextDeleting.add(action.fileId)
      return { ...state, deletingFileIds: nextDeleting }
    }

    case 'DELETE_COMPLETE': {
      const nextDeleting = new Set(state.deletingFileIds)
      nextDeleting.delete(action.fileId)
      return {
        ...state,
        deletingFileIds: nextDeleting,
        files: state.files.filter((file) => file.file_id !== action.fileId),
      }
    }

    case 'REINGEST_START': {
      const next = new Set(state.reingestingFileIds)
      next.add(action.fileId)
      return { ...state, reingestingFileIds: next }
    }

    case 'REINGEST_COMPLETE': {
      const next = new Set(state.reingestingFileIds)
      next.delete(action.fileId)
      return { ...state, reingestingFileIds: next }
    }

    case 'OPEN_REVIEW':
      return {
        ...state,
        activeReviewFileId: action.fileId,
        reviewStatesByFileId: {
          ...state.reviewStatesByFileId,
          [action.fileId]: state.reviewStatesByFileId[action.fileId] || 'awaiting review',
        },
      }

    case 'CLOSE_REVIEW':
      return { ...state, activeReviewFileId: null }

    case 'REVIEW_CASE_SUCCESS':
      return {
        ...state,
        reviewCasesByFileId: {
          ...state.reviewCasesByFileId,
          [action.fileId]: action.reviewCase,
        },
        reviewErrorsByFileId: {
          ...state.reviewErrorsByFileId,
          [action.fileId]: null,
        },
        reviewStatesByFileId: {
          ...state.reviewStatesByFileId,
          [action.fileId]: 'awaiting review',
        },
      }

    case 'REVIEW_CASE_ERROR':
      return {
        ...state,
        reviewErrorsByFileId: {
          ...state.reviewErrorsByFileId,
          [action.fileId]: action.error,
        },
      }

    case 'REVIEW_DECISION_START':
      return {
        ...state,
        reviewStatesByFileId: {
          ...state.reviewStatesByFileId,
          [action.fileId]: 'decision submitting',
        },
      }

    case 'REVIEW_DECISION_COMPLETE':
      return {
        ...state,
        activeReviewFileId: null,
        reviewStatesByFileId: {
          ...state.reviewStatesByFileId,
          [action.fileId]: action.nextState,
        },
      }

    case 'SUMMARY_LOADING_START': {
      const next = new Set(state.summaryLoadingFileIds)
      next.add(action.fileId)
      return { ...state, summaryLoadingFileIds: next }
    }

    case 'SUMMARY_LOADING_DONE': {
      const next = new Set(state.summaryLoadingFileIds)
      next.delete(action.fileId)
      return { ...state, summaryLoadingFileIds: next }
    }

    case 'SUMMARY_SUCCESS':
      return {
        ...state,
        summaryByFileId: {
          ...state.summaryByFileId,
          [action.fileId]: action.summary,
        },
        activeSummaryFileId: action.fileId,
      }

    case 'OPEN_SUMMARY':
      return { ...state, activeSummaryFileId: action.fileId }

    case 'CLOSE_SUMMARY':
      return { ...state, activeSummaryFileId: null }

    default:
      return state
  }
}

export function useFiles() {
  const reduxDispatch = useDispatch()
  const cachedFiles = useSelector(selectCachedFiles)

  const [state, dispatchState] = useReducer(filesReducer, undefined, () =>
    buildInitialState(cachedFiles)
  )
  const pollPendingRef = useRef(false)

  const loadFiles = useCallback(async () => {
    dispatchState({ type: 'LOAD_START' })
    try {
      const data = await fileService.getFiles()
      const files = data.files || []
      dispatchState({ type: 'LOAD_SUCCESS', files })
      reduxDispatch(setFiles(files))
    } catch (error) {
      console.error('Error loading files:', error)
      dispatchState({ type: 'LOAD_ERROR' })
    }
  }, [reduxDispatch])

  useEffect(() => {
    let cancelled = false

    const poll = async () => {
      if (pollPendingRef.current) return
      pollPendingRef.current = true
      try {
        const data = await fileService.getFiles()
        if (!cancelled) {
          const files = data.files || []
          dispatchState({ type: 'LOAD_SUCCESS', files })
          reduxDispatch(setFiles(files))
        }
      } catch (error) {
        if (!cancelled) {
          console.error('Error loading files:', error)
          dispatchState({ type: 'LOAD_ERROR' })
        }
      } finally {
        pollPendingRef.current = false
      }
    }

    poll()
    const interval = setInterval(poll, 5000)
    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [reduxDispatch])

  const uploadFiles = useCallback(async (filesToUpload) => {
    dispatchState({ type: 'UPLOAD_START' })
    try {
      const responses = []
      for (const file of filesToUpload) {
        const response = await fileService.uploadFile(file)
        responses.push(response)
        dispatchState({ type: 'UPLOAD_RESPONSE', response, file })
      }
      await loadFiles()
      reduxDispatch(filesChanged())
      return responses
    } catch (error) {
      console.error('Error uploading files:', error)
      throw error
    } finally {
      dispatchState({ type: 'UPLOAD_COMPLETE' })
    }
  }, [reduxDispatch, loadFiles])

  const deleteFile = useCallback(async (fileId) => {
    if (state.deletingFileIds.has(fileId)) return

    dispatchState({ type: 'DELETE_START', fileId })
    try {
      await fileService.deleteFile(fileId)
      reduxDispatch(filesChanged())
      await loadFiles()
    } catch (error) {
      console.error('Error deleting file:', error)
      throw error
    } finally {
      dispatchState({ type: 'DELETE_COMPLETE', fileId })
    }
  }, [reduxDispatch, loadFiles, state.deletingFileIds])

  const rerunIngestion = useCallback(async (fileId) => {
    if (state.reingestingFileIds.has(fileId)) return

    dispatchState({ type: 'REINGEST_START', fileId })
    try {
      await fileService.rerunStage(fileId, 'ingestion')
      await loadFiles()
    } catch (error) {
      console.error('Error re-running ingestion:', error)
      throw error
    } finally {
      dispatchState({ type: 'REINGEST_COMPLETE', fileId })
    }
  }, [loadFiles, state.reingestingFileIds])

  const openSummary = useCallback(async (fileId) => {
    // If already cached, just open it
    if (state.summaryByFileId[fileId]) {
      dispatchState({ type: 'OPEN_SUMMARY', fileId })
      return
    }

    dispatchState({ type: 'SUMMARY_LOADING_START', fileId })
    try {
      const data = await fileService.getFileSummary(fileId)
      dispatchState({ type: 'SUMMARY_SUCCESS', fileId, summary: data })
    } catch (error) {
      console.error('Error loading summary:', error)
      throw error
    } finally {
      dispatchState({ type: 'SUMMARY_LOADING_DONE', fileId })
    }
  }, [state.summaryByFileId])

  const closeSummary = useCallback(() => {
    dispatchState({ type: 'CLOSE_SUMMARY' })
  }, [])

  const openReview = useCallback(async (fileId) => {
    dispatchState({ type: 'OPEN_REVIEW', fileId })
    try {
      const reviewCase = await fileService.getReviewCase(fileId)
      dispatchState({ type: 'REVIEW_CASE_SUCCESS', fileId, reviewCase })
      return reviewCase
    } catch (error) {
      console.error('Error fetching review case:', error)
      dispatchState({
        type: 'REVIEW_CASE_ERROR',
        fileId,
        error: error?.message || 'Failed to load review case',
      })
      throw error
    }
  }, [])

  const closeReview = useCallback(() => {
    dispatchState({ type: 'CLOSE_REVIEW' })
  }, [])

  const submitReviewDecision = useCallback(async (fileId, payload) => {
    dispatchState({ type: 'REVIEW_DECISION_START', fileId })
    try {
      const response = await fileService.submitReviewDecision(fileId, payload)
      const status = normalizeFileStatus(response.file_status)
      const nextState = status === 'rejected' ? 'rejected' : 'resumed'
      dispatchState({ type: 'REVIEW_DECISION_COMPLETE', fileId, nextState })
      reduxDispatch(filesChanged())
      await loadFiles()
      return response
    } catch (error) {
      console.error('Error submitting review decision:', error)
      dispatchState({
        type: 'REVIEW_DECISION_COMPLETE',
        fileId,
        nextState: 'awaiting review',
      })
      throw error
    }
  }, [reduxDispatch, loadFiles])

  return {
    files: state.files,
    loading: state.loading,
    uploading: state.uploading,
    deletingFileIds: state.deletingFileIds,
    reingestingFileIds: state.reingestingFileIds,
    recentUploads: state.recentUploads,
    reviewStatesByFileId: state.reviewStatesByFileId,
    reviewCasesByFileId: state.reviewCasesByFileId,
    reviewErrorsByFileId: state.reviewErrorsByFileId,
    summaryByFileId: state.summaryByFileId,
    summaryLoadingFileIds: state.summaryLoadingFileIds,
    activeSummaryFileId: state.activeSummaryFileId,
    activeReviewFileId: state.activeReviewFileId,
    loadFiles,
    uploadFiles,
    deleteFile,
    rerunIngestion,
    openSummary,
    closeSummary,
    openReview,
    closeReview,
    submitReviewDecision,
  }
}
