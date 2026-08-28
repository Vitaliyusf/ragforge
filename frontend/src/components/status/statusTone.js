/**
 * The one status vocabulary the app presents with.
 *
 * Before this module every surface picked its own colour for "it worked" and
 * its own word for "it is running", and three of them reached for raw hex.
 * A tone is the presentation layer only — features keep owning what their
 * states *mean* and map onto a tone here.
 *
 * Every tone carries a default icon as well as a colour, because status is
 * never allowed to be conveyed by colour alone.
 */

import { AlertTriangle, CheckCircle2, CircleDot, Info, Loader2, XCircle } from 'lucide-react'

export const STATUS_TONES = {
  NEUTRAL: 'neutral',
  INFO: 'info',
  LIVE: 'live',
  SUCCESS: 'success',
  WARNING: 'warning',
  DANGER: 'danger',
}

/**
 * @typedef {Object} StatusTone
 * @property {string} fg      foreground/icon colour token
 * @property {string} bg      soft background token
 * @property {string} border  border token
 * @property {Function} icon  default lucide icon — the non-colour cue
 * @property {boolean} live   whether continuous motion is allowed for this tone
 */

/** @type {Record<string, StatusTone>} */
export const STATUS_TONE = {
  neutral: {
    fg: 'var(--fg-muted)',
    bg: 'var(--surface-hover)',
    border: 'var(--border)',
    icon: CircleDot,
    live: false,
  },
  info: {
    fg: 'var(--info)',
    bg: 'var(--info-soft)',
    border: 'transparent',
    icon: Info,
    live: false,
  },
  // The only tone allowed a continuous animation: something really is moving.
  live: {
    fg: 'var(--status-live)',
    bg: 'var(--accent-soft)',
    border: 'transparent',
    icon: Loader2,
    live: true,
  },
  success: {
    fg: 'var(--success)',
    bg: 'var(--success-soft)',
    border: 'transparent',
    icon: CheckCircle2,
    live: false,
  },
  warning: {
    fg: 'var(--warning)',
    bg: 'var(--warning-soft)',
    border: 'transparent',
    icon: AlertTriangle,
    live: false,
  },
  danger: {
    fg: 'var(--danger)',
    bg: 'var(--danger-soft)',
    border: 'transparent',
    icon: XCircle,
    live: false,
  },
}

/**
 * Names that predate the tone vocabulary and still appear at call sites.
 * They resolve to a tone rather than being duplicated as separate entries.
 */
const TONE_ALIASES = {
  default: 'neutral',
  error: 'danger',
  accent: 'live',
  processing: 'live',
  running: 'live',
}

/**
 * Resolve any tone name or legacy alias to a tone key.
 * @param {string} name
 * @returns {string} a key of STATUS_TONE
 */
export function resolveToneName(name) {
  const key = String(name || '').toLowerCase()
  if (STATUS_TONE[key]) return key
  return TONE_ALIASES[key] ?? STATUS_TONES.NEUTRAL
}

/**
 * Resolve any tone name or legacy alias to its presentation record.
 * @param {string} name
 * @returns {StatusTone}
 */
export function resolveTone(name) {
  return STATUS_TONE[resolveToneName(name)]
}
