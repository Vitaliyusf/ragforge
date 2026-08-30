import { toast } from 'sonner'

/**
 * One place for every transient notification the app raises.
 *
 * The rules this encodes, so that call sites do not each re-decide them:
 *
 * - A success is short and never blocks. Routine success gets a toast, not a
 *   modal — the work already happened, there is nothing to confirm.
 * - An error stays long enough to read and, wherever the caller can offer one,
 *   carries the recovery action instead of leaving the user to hunt for it.
 * - A critical failure — something the workspace cannot proceed without — does
 *   not auto-dismiss. It is dismissed by the person, not by a timer.
 *
 * Durations are exported so tests assert the policy rather than a literal.
 */
export const NOTIFY_DURATION = {
  /** Long enough to register, short enough to stay out of the way. */
  success: 3000,
  /** Long enough to read a message plus a service name and act on it. */
  error: 8000,
  /** Never auto-dismissed. */
  critical: Infinity,
}

/** Normalise whatever a rejected call threw into something readable. */
export function describeError(error, fallback = 'Please try again.') {
  const message = typeof error === 'string' ? error : error?.message
  return message?.trim() || fallback
}

/** Short, non-blocking confirmation that work completed. */
export function notifySuccess(message, { description } = {}) {
  return toast.success(message, {
    description,
    duration: NOTIFY_DURATION.success,
  })
}

/**
 * A recoverable failure. Pass `onRetry` whenever the caller can actually run
 * the failed operation again — an error the user can only read is a dead end.
 */
export function notifyError(message, { description, error, onRetry, retryLabel = 'Retry' } = {}) {
  return toast.error(message, {
    description: description ?? (error === undefined ? undefined : describeError(error)),
    duration: NOTIFY_DURATION.error,
    action: onRetry ? { label: retryLabel, onClick: onRetry } : undefined,
  })
}

/**
 * A failure that leaves the workspace unusable until it is dealt with, so it
 * stays on screen until dismissed. Reserve this for the cases that really are
 * blocking; a persistent toast for a routine error is just noise that will not
 * go away.
 */
export function notifyCritical(message, { description, error, onRetry, retryLabel = 'Retry' } = {}) {
  return toast.error(message, {
    description: description ?? (error === undefined ? undefined : describeError(error)),
    duration: NOTIFY_DURATION.critical,
    dismissible: true,
    action: onRetry ? { label: retryLabel, onClick: onRetry } : undefined,
  })
}
