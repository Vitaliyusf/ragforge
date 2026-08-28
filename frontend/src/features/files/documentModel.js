/**
 * The Documents view model.
 *
 * One place decides what a document's row says: its user-facing status, the
 * pipeline stage that status came from, and how a failure reads. Every other
 * Files component consumes this module rather than re-deriving the same facts
 * from `status` and `stage` on its own.
 *
 * Nothing here invents state. The stage keys and their order are the ones
 * `create_file_document()` writes, the statuses are the ones the files service
 * stores, and a field the backend never sends is reported as absent rather
 * than as a zero.
 */

import { STATUS_TONES } from '@/components/status/statusTone'
import { computeEffectiveStatus } from './fileStatus'

/**
 * The ingestion pipeline, in the order the files service writes it.
 *
 * `active` is what the stage is called while it runs, `done` what it is called
 * once it has. Both are used verbatim in the Pipeline column, so a processing
 * row reads "Embedding…" and a finished one "Indexed".
 */
export const PIPELINE_STAGES = [
  { key: 'extraction', label: 'Extraction', active: 'Extracting', done: 'Extracted' },
  { key: 'review', label: 'Review', active: 'In review', done: 'Reviewed' },
  { key: 'chunking', label: 'Chunking', active: 'Chunking', done: 'Chunked' },
  { key: 'summary', label: 'Summary', active: 'Summarising', done: 'Summarised' },
  { key: 'embedding', label: 'Embedding', active: 'Embedding', done: 'Embedded' },
  { key: 'semantic', label: 'Semantic', active: 'Analysing', done: 'Analysed' },
  { key: 'vector', label: 'Indexing', active: 'Indexing', done: 'Indexed' },
  { key: 'metadata', label: 'Metadata', active: 'Tagging', done: 'Tagged' },
]

const STAGE_DONE_VALUES = new Set(['done', 'complete', 'completed', 'ready'])
const STAGE_SKIPPED_VALUES = new Set(['skipped', 'not_required'])
const STAGE_RUNNING_VALUES = new Set(['running', 'processing'])

/**
 * Collapse a raw `stage.*` value onto the states the UI draws.
 * @param {unknown} value
 * @returns {'done'|'skipped'|'running'|'paused'|'failed'|'waiting'}
 */
export function normalizeStageValue(value) {
  const normalized = String(value ?? 'waiting').trim().toLowerCase()
  if (STAGE_DONE_VALUES.has(normalized)) return 'done'
  if (STAGE_SKIPPED_VALUES.has(normalized)) return 'skipped'
  if (STAGE_RUNNING_VALUES.has(normalized)) return 'running'
  if (normalized === 'paused') return 'paused'
  if (normalized === 'error') return 'failed'
  return 'waiting'
}

/**
 * The per-stage view of one document, in pipeline order.
 * @param {{stage?: Record<string, string>}} file
 * @returns {Array<{key: string, label: string, value: string, state: string}>}
 */
export function getPipelineStages(file) {
  const stage = file?.stage
  if (!stage || typeof stage !== 'object') return []
  return PIPELINE_STAGES.map((descriptor) => ({
    ...descriptor,
    value: stage[descriptor.key] ?? 'waiting',
    state: normalizeStageValue(stage[descriptor.key]),
  }))
}

/** The canonical UI status vocabulary — what the filter and the badge share. */
export const DOCUMENT_STATUSES = {
  READY: 'ready',
  PROCESSING: 'processing',
  QUEUED: 'queued',
  REVIEW: 'review',
  FAILED: 'failed',
  REJECTED: 'rejected',
  UNKNOWN: 'unknown',
}

const STATUS_PRESENTATION = {
  [DOCUMENT_STATUSES.READY]: { label: 'Ready', tone: STATUS_TONES.SUCCESS },
  // The one status where something really is moving, and so the only one
  // allowed the live tone and its motion.
  [DOCUMENT_STATUSES.PROCESSING]: { label: 'Processing', tone: STATUS_TONES.LIVE },
  [DOCUMENT_STATUSES.QUEUED]: { label: 'Queued', tone: STATUS_TONES.NEUTRAL },
  [DOCUMENT_STATUSES.REVIEW]: { label: 'Needs review', tone: STATUS_TONES.WARNING },
  [DOCUMENT_STATUSES.FAILED]: { label: 'Failed', tone: STATUS_TONES.DANGER },
  [DOCUMENT_STATUSES.REJECTED]: { label: 'Rejected', tone: STATUS_TONES.DANGER },
  [DOCUMENT_STATUSES.UNKNOWN]: { label: 'Unknown', tone: STATUS_TONES.NEUTRAL },
}

/** The status filter options, in the order the toolbar shows them. */
export const STATUS_FILTER_OPTIONS = [
  { value: 'all', label: 'All statuses' },
  { value: DOCUMENT_STATUSES.READY, label: 'Ready' },
  { value: DOCUMENT_STATUSES.PROCESSING, label: 'Processing' },
  { value: DOCUMENT_STATUSES.QUEUED, label: 'Queued' },
  { value: DOCUMENT_STATUSES.REVIEW, label: 'Needs review' },
  { value: DOCUMENT_STATUSES.FAILED, label: 'Failed' },
  { value: DOCUMENT_STATUSES.REJECTED, label: 'Rejected' },
]

/**
 * Map the backend's effective status onto the UI vocabulary.
 *
 * `started` with nothing yet running is the one case that needs the stage
 * map: the service writes that status at upload, before extraction picks the
 * file up, and calling that "Processing" would claim work that has not begun.
 * @param {object} file
 * @returns {string} a DOCUMENT_STATUSES value
 */
export function getDocumentStatus(file) {
  const effective = computeEffectiveStatus(file)
  switch (effective) {
    case 'complete':
      return DOCUMENT_STATUSES.READY
    case 'awaiting_review':
      return DOCUMENT_STATUSES.REVIEW
    case 'rejected':
      return DOCUMENT_STATUSES.REJECTED
    case 'error':
      return DOCUMENT_STATUSES.FAILED
    case 'processing': {
      const stages = getPipelineStages(file)
      const started = stages.some((stage) => stage.state !== 'waiting')
      return started ? DOCUMENT_STATUSES.PROCESSING : DOCUMENT_STATUSES.QUEUED
    }
    default:
      return DOCUMENT_STATUSES.UNKNOWN
  }
}

/**
 * Label and tone for a UI status.
 * @param {string} status a DOCUMENT_STATUSES value
 */
export function getStatusPresentation(status) {
  return STATUS_PRESENTATION[status] ?? STATUS_PRESENTATION[DOCUMENT_STATUSES.UNKNOWN]
}

/**
 * The single line the Pipeline column shows.
 *
 * A ready document says "Indexed" once — not eight ticks — and a working one
 * names the stage that is actually running. `state` is what the row uses to
 * decide whether motion is warranted.
 *
 * @param {object} file
 * @returns {{state: string, label: string, stageKey: string|null}}
 */
export function summarizePipeline(file) {
  const status = getDocumentStatus(file)
  const stages = getPipelineStages(file)

  const failed = stages.find((stage) => stage.state === 'failed')
  if (failed) return { state: 'failed', label: failed.label, stageKey: failed.key }

  if (status === DOCUMENT_STATUSES.READY) {
    return { state: 'done', label: 'Indexed', stageKey: 'vector' }
  }
  if (status === DOCUMENT_STATUSES.FAILED) {
    // Errored with no stage flag of its own: the run failed before, or
    // outside, any single stage.
    return { state: 'failed', label: 'Ingestion', stageKey: null }
  }
  if (status === DOCUMENT_STATUSES.REVIEW) {
    return { state: 'blocked', label: 'Awaiting review', stageKey: 'review' }
  }
  if (status === DOCUMENT_STATUSES.REJECTED) {
    return { state: 'blocked', label: 'Stopped at review', stageKey: 'review' }
  }

  const running = stages.find((stage) => stage.state === 'running')
  if (running) return { state: 'running', label: `${running.active}…`, stageKey: running.key }

  const lastDone = [...stages].reverse().find((stage) => stage.state === 'done')
  if (lastDone) return { state: 'idle', label: lastDone.done, stageKey: lastDone.key }

  return { state: 'queued', label: 'Not started', stageKey: null }
}

/**
 * What a failed document needs to say: what broke, why, and what it costs.
 *
 * The files service stores no error string on the file document, so `reason`
 * is only ever a reason recorded on a real audit event. When no event carries
 * one this reports `null` rather than inventing a cause.
 *
 * @param {object} file
 * @param {Array<object>} [events] audit events, newest first
 * @returns {{title: string, reason: string|null, impact: string}|null}
 */
export function describeFailure(file, events = []) {
  if (getDocumentStatus(file) !== DOCUMENT_STATUSES.FAILED) return null

  const pipeline = summarizePipeline(file)
  const failureEvent = (events || []).find(
    (event) => String(event?.to_status || '').toLowerCase() === 'error'
      || String(event?.event_type || '').includes('failed')
  )
  const detail = failureEvent?.details
  const reason = failureEvent?.reason
    || (typeof detail?.error === 'string' ? detail.error : null)
    || null

  return {
    title: `${pipeline.label} failed`,
    reason,
    impact: 'This document is not searchable.',
  }
}

/**
 * The short type label for the Type column: the filename extension when there
 * is one, otherwise the MIME subtype. `application/octet-stream` earns none.
 * @param {object} file
 * @returns {string|null}
 */
export function getDocumentType(file) {
  const filename = String(file?.filename || '')
  const extension = filename.includes('.') ? filename.split('.').pop() : ''
  if (extension && extension.length <= 5) return extension.toUpperCase()

  const contentType = String(file?.content_type || '').toLowerCase()
  if (!contentType || contentType === 'application/octet-stream') return null
  const subtype = contentType.split('/').pop()
  return subtype ? subtype.toUpperCase() : null
}

/** The columns a document list can be ordered by. */
export const SORT_OPTIONS = [
  { value: 'updated', label: 'Updated' },
  { value: 'name', label: 'Name' },
  { value: 'status', label: 'Status' },
  { value: 'size', label: 'Size' },
]

/** Attention first: failure, then review, then work in flight, then settled. */
const STATUS_SORT_RANK = {
  [DOCUMENT_STATUSES.FAILED]: 0,
  [DOCUMENT_STATUSES.REVIEW]: 1,
  [DOCUMENT_STATUSES.PROCESSING]: 2,
  [DOCUMENT_STATUSES.QUEUED]: 3,
  [DOCUMENT_STATUSES.READY]: 4,
  [DOCUMENT_STATUSES.REJECTED]: 5,
  [DOCUMENT_STATUSES.UNKNOWN]: 6,
}

function timestampOf(file) {
  const raw = file?.updated_at || file?.created_at
  const parsed = raw ? Date.parse(raw) : NaN
  return Number.isNaN(parsed) ? 0 : parsed
}

/**
 * Search, filter and sort in one pass over the list.
 *
 * Search runs over metadata the list request already carries — filename,
 * content type and owner — so it never costs a request of its own.
 *
 * `desc` means "most interesting first" for every column: newest, Z→A,
 * largest, most urgent.
 *
 * @param {Array<object>} files
 * @param {{query?: string, status?: string, sort?: string, direction?: 'asc'|'desc'}} view
 * @returns {Array<object>}
 */
export function selectDocuments(files, view = {}) {
  const { query = '', status = 'all', sort = 'updated', direction = 'desc' } = view
  const needle = query.trim().toLocaleLowerCase()

  const filtered = (files || []).filter((file) => {
    if (status !== 'all' && getDocumentStatus(file) !== status) return false
    if (!needle) return true
    return [file.filename, file.content_type, file.owner_display_name, file.owner_email]
      .some((field) => String(field || '').toLocaleLowerCase().includes(needle))
  })

  const sign = direction === 'asc' ? 1 : -1
  const comparators = {
    name: (a, b) => String(a.filename || '').localeCompare(String(b.filename || '')) * sign,
    size: (a, b) => ((a.size || 0) - (b.size || 0)) * sign,
    status: (a, b) =>
      (STATUS_SORT_RANK[getDocumentStatus(b)] - STATUS_SORT_RANK[getDocumentStatus(a)]) * sign,
    updated: (a, b) => (timestampOf(a) - timestampOf(b)) * sign,
  }

  return filtered.sort(comparators[sort] ?? comparators.updated)
}

/** Counts per UI status, for the toolbar's filter labels. */
export function countByStatus(files) {
  const counts = { all: (files || []).length }
  for (const file of files || []) {
    const status = getDocumentStatus(file)
    counts[status] = (counts[status] || 0) + 1
  }
  return counts
}
