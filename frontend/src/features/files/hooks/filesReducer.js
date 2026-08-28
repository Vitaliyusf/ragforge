/**
 * Local reducer backing the Files tab.
 *
 * Holds the optimistic UI transitions — pending deletes, in-flight
 * re-indexes, the open review panel — separately from the fetched file list.
 */

import { normalizeFileStatus } from '@/features/files/fileStatus'

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

/** Shallow value equality, one level deep into plain objects and arrays. */
function isEquivalent(a, b) {
  if (a === b) return true
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false
  if (Array.isArray(a) || Array.isArray(b)) {
    return Array.isArray(a) && Array.isArray(b)
      && a.length === b.length
      && a.every((item, index) => item === b[index])
  }
  const keys = Object.keys(a)
  if (keys.length !== Object.keys(b).length) return false
  return keys.every((key) => a[key] === b[key])
}

/**
 * Replace the list, keeping the object identity of every unchanged record.
 *
 * The list is refetched every five seconds. Without this, each poll hands
 * every row a brand-new object, every memoised row re-renders, and the one
 * document whose stage actually moved is indistinguishable from the 999 that
 * did not. Reusing the previous object is what lets `memo` do its job.
 */
function mergePreservingIdentity(previousFiles, nextFiles) {
  const previousById = new Map(previousFiles.map((file) => [file.file_id, file]))
  return nextFiles.map((file) => {
    const normalized = normalizeFileRecord(file)
    const previous = previousById.get(normalized.file_id)
    if (!previous) return normalized

    const keys = Object.keys(normalized)
    const unchanged = keys.length === Object.keys(previous).length
      && keys.every((key) => isEquivalent(previous[key], normalized[key]))
    return unchanged ? previous : normalized
  })
}

export function buildInitialState(cachedFiles) {
  return {
    files: cachedFiles.map(normalizeFileRecord),
    loading: false,
    uploading: false,
    deletingFileIds: new Set(),
    reingestingFileIds: new Set(),
    reviewStatesByFileId: {},
    reviewCasesByFileId: {},
    reviewErrorsByFileId: {},
    activeReviewFileId: null,
  }
}

export function filesReducer(state, action) {
  switch (action.type) {
    case 'LOAD_START':
      return { ...state, loading: true }

    case 'LOAD_SUCCESS': {
      const nextReviewStates = { ...state.reviewStatesByFileId }
      const normalizedFiles = mergePreservingIdentity(state.files, action.files)

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

    default:
      return state
  }
}
