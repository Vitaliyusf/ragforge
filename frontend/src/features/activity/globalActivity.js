/**
 * One global answer to "is anything happening?".
 *
 * The header used to carry several small claims about liveness — a lit dot on
 * the logo that was on permanently, a "Live" chip beside the composer, another
 * in the log stream — none of which agreed and none of which meant the same
 * thing. This collapses them into a single control with one state.
 *
 * It derives, and never fetches. Every item comes from an activity a feature
 * actually published, so the control cannot claim work the backend has not
 * reported.
 */

import { PRODUCT_LABELS } from '@/lib/terminology'
import { STATUS_DOMAINS, describeStatus } from '@/components/status/statusDomains'
import {
  ACTIVITY_FEATURES,
  ACTIVITY_STATES,
  isActiveState,
  normalizeActivity,
} from './activityModel'

export const GLOBAL_ACTIVITY_STATES = Object.freeze({
  READY: 'ready',
  ACTIVE: 'active',
  DEGRADED: 'degraded',
  DISCONNECTED: 'disconnected',
})

/** Feature → the destination name the popover lists work under. */
const FEATURE_LABELS = Object.freeze({
  [ACTIVITY_FEATURES.CHAT]: PRODUCT_LABELS.chat,
  [ACTIVITY_FEATURES.FILES]: PRODUCT_LABELS.knowledge,
  [ACTIVITY_FEATURES.EVAL]: PRODUCT_LABELS.eval,
})

/**
 * What each feature's work is called in the popover.
 *
 * Plain nouns, because the list answers "what is running", not "what state is
 * this in" — the state is rendered beside it from the execution domain.
 */
const FEATURE_WORK = Object.freeze({
  [ACTIVITY_FEATURES.CHAT]: 'Answer generation',
  [ACTIVITY_FEATURES.FILES]: 'Indexing',
  [ACTIVITY_FEATURES.EVAL]: 'Evaluation',
})

/** Activity state → the execution-domain state it is reported as. */
const EXECUTION_STATE = Object.freeze({
  [ACTIVITY_STATES.QUEUED]: 'queued',
  [ACTIVITY_STATES.RUNNING]: 'running',
  [ACTIVITY_STATES.SUCCESS]: 'completed',
  [ACTIVITY_STATES.WARNING]: 'partial',
  [ACTIVITY_STATES.FAILED]: 'failed',
})

/** Popover order: running work first, then anything that needs attention. */
const ITEM_ORDER = [
  ACTIVITY_STATES.RUNNING,
  ACTIVITY_STATES.QUEUED,
  ACTIVITY_STATES.FAILED,
  ACTIVITY_STATES.WARNING,
  ACTIVITY_STATES.SUCCESS,
]

function progressText(progress) {
  return progress ? `${progress.completed}/${progress.total}` : null
}

/**
 * @typedef {Object} GlobalActivityItem
 * @property {string} feature       the destination id the work belongs to
 * @property {string} featureLabel  the destination's canonical name
 * @property {string} work          what is being done
 * @property {string} state         an execution-domain state
 * @property {string} stateLabel    its canonical label
 * @property {string} tone          its tone
 * @property {?string} detail       progress or a bounded label, when real
 */

/**
 * Collapse every published activity into one control state.
 *
 * @param {Record<string, Object>} activities the activity store
 * @param {{online?: boolean}} [options] browser connectivity
 * @returns {{state: string, label: string, tone: string, activeCount: number,
 *   items: GlobalActivityItem[]}}
 */
export function summarizeActivity(activities = {}, { online = true } = {}) {
  const items = []
  let activeCount = 0
  let failed = 0

  for (const feature of Object.keys(FEATURE_LABELS)) {
    const activity = normalizeActivity(activities[feature])
    if (activity.state === ACTIVITY_STATES.IDLE) continue

    const executionState = EXECUTION_STATE[activity.state]
    if (!executionState) continue
    const status = describeStatus(STATUS_DOMAINS.EXECUTION, executionState)
    if (isActiveState(activity.state)) activeCount += 1
    if (activity.state === ACTIVITY_STATES.FAILED) failed += 1

    items.push({
      feature,
      featureLabel: FEATURE_LABELS[feature],
      work: FEATURE_WORK[feature],
      state: status.state,
      stateLabel: status.label,
      tone: status.tone,
      detail: progressText(activity.progress) || activity.label || null,
      rank: ITEM_ORDER.indexOf(activity.state),
    })
  }

  items.sort((a, b) => a.rank - b.rank)

  // Connectivity outranks everything: with the browser offline nothing the
  // store holds is current, and claiming "2 active" would be a guess.
  if (!online) {
    const status = describeStatus(STATUS_DOMAINS.CONNECTIVITY, 'disconnected')
    return {
      state: GLOBAL_ACTIVITY_STATES.DISCONNECTED,
      label: status.label,
      tone: status.tone,
      activeCount,
      items,
    }
  }

  if (failed > 0) {
    return {
      state: GLOBAL_ACTIVITY_STATES.DEGRADED,
      label: 'Degraded',
      tone: 'warning',
      activeCount,
      items,
    }
  }

  if (activeCount > 0) {
    return {
      state: GLOBAL_ACTIVITY_STATES.ACTIVE,
      label: `${activeCount} active`,
      tone: 'live',
      activeCount,
      items,
    }
  }

  return {
    state: GLOBAL_ACTIVITY_STATES.READY,
    label: 'Ready',
    tone: 'success',
    activeCount: 0,
    items,
  }
}
