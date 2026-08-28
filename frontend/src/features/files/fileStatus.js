/**
 * File ingestion status semantics.
 *
 * These are the Files domain's own states — they mirror what the backend
 * reports and this module does not invent any. Presentation (colour, icon,
 * accessible label) lives in `@/components/status`; this module only maps a
 * server value onto a normalised state, a human label and a status tone.
 */

import { STATUS_TONES } from '@/components/status/statusTone'

/** Terminal states: the pipeline will not move them on its own. */
const TERMINAL = ['complete', 'rejected', 'awaiting_review', 'error']

const STAGE_DONE = ['done', 'complete', 'completed', 'ready', 'skipped', 'not_required']

/**
 * Collapse the many server spellings of a status onto one vocabulary.
 * @param {string} status
 * @returns {string}
 */
export function normalizeFileStatus(status) {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'awaiting_review') return 'awaiting_review'
  if (['started', 'processing', 'resuming', 'running'].includes(normalized)) return 'processing'
  if (['complete', 'completed', 'ready', 'done'].includes(normalized)) return 'complete'
  if (normalized === 'rejected') return 'rejected'
  if (normalized === 'error') return 'error'
  return normalized || 'unknown'
}

/**
 * The effective status, using stage sub-fields to correct a stale top-level
 * value. When every stage has finished but the top-level status has not been
 * flushed yet, this reports `complete` rather than `processing`.
 * @param {{status?: string, stage?: Record<string, string>}} file
 * @returns {string}
 */
export function computeEffectiveStatus(file) {
  const topLevel = normalizeFileStatus(file?.status)
  if (TERMINAL.includes(topLevel)) return topLevel

  const stage = file?.stage
  if (stage && typeof stage === 'object') {
    const values = Object.values(stage)
    if (values.length > 0) {
      if (values.some((v) => v === 'error')) return 'error'
      if (values.every((v) => STAGE_DONE.includes(v))) return 'complete'
    }
  }

  return topLevel
}

/**
 * Map a file status onto a shared status tone.
 *
 * The Documents table owns its own richer status vocabulary in
 * `documentModel.js`; this mapping remains for the uploader surface, which
 * shows the raw lifecycle status of a file it has just handed over.
 */
const STATUS_TONE_BY_STATE = {
  complete: STATUS_TONES.SUCCESS,
  // Something really is moving, so this is the one tone allowed motion.
  processing: STATUS_TONES.LIVE,
  awaiting_review: STATUS_TONES.WARNING,
  rejected: STATUS_TONES.DANGER,
  error: STATUS_TONES.DANGER,
}

export function getFileStatusTone(status) {
  return STATUS_TONE_BY_STATE[normalizeFileStatus(status)] ?? STATUS_TONES.NEUTRAL
}

export function hasReviewPending(file) {
  return normalizeFileStatus(file?.status) === 'awaiting_review' || file?.review_status === 'pending'
}
