'use client'

/**
 * Global activity state for the primary navigation.
 *
 * One bounded entry per feature, published by whichever source owns that
 * feature's truth. The provider itself never fetches: it is a store plus a
 * registry of live sources, so a feature page that is already polling can
 * claim ownership and stop the background fallback from polling the same
 * thing twice.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef } from 'react'
import {
  ACTIVITY_FEATURES,
  IDLE_ACTIVITY,
  acknowledgeActivity,
  normalizeActivity,
} from './activityModel'

const ActivityContext = createContext(null)

const INITIAL_STATE = {
  activities: {
    [ACTIVITY_FEATURES.EVAL]: { ...IDLE_ACTIVITY },
    [ACTIVITY_FEATURES.CHAT]: { ...IDLE_ACTIVITY },
    [ACTIVITY_FEATURES.FILES]: { ...IDLE_ACTIVITY },
  },
  /**
   * The exact entry the user has already seen, per feature.
   *
   * Acknowledgement has to outlive the entry it cleared: the source that
   * produced a finished run keeps re-publishing it on every poll, and
   * without this the dot the user just dismissed would light straight back
   * up. A different result publishes normally.
   */
  acknowledged: {},
}

function signature(entry) {
  if (!entry) return ''
  return [
    entry.state,
    entry.label || '',
    entry.completedAt || '',
    entry.count ?? '',
    entry.progress ? `${entry.progress.completed}/${entry.progress.total}` : '',
  ].join('|')
}

function sameEntry(a, b) {
  if (a === b) return true
  if (!a || !b) return false
  const keys = new Set([...Object.keys(a), ...Object.keys(b)])
  for (const key of keys) {
    if (key === 'progress') {
      if (a.progress?.completed !== b.progress?.completed) return false
      if (a.progress?.total !== b.progress?.total) return false
    } else if (a[key] !== b[key]) return false
  }
  return true
}

function reducer(state, action) {
  switch (action.type) {
    case 'PUBLISH': {
      const next = normalizeActivity(action.entry)
      if (state.acknowledged[action.feature] === signature(next)) return state
      // Sources publish derived objects on every render; without this the
      // store would hand back a new object each time and spin the effects
      // that read it.
      if (sameEntry(state.activities[action.feature], next)) return state
      return {
        activities: { ...state.activities, [action.feature]: next },
        acknowledged: { ...state.acknowledged, [action.feature]: undefined },
      }
    }
    case 'ACKNOWLEDGE': {
      const current = state.activities[action.feature]
      const next = acknowledgeActivity(current)
      if (sameEntry(current, next)) return state
      return {
        activities: { ...state.activities, [action.feature]: next },
        acknowledged: { ...state.acknowledged, [action.feature]: signature(current) },
      }
    }
    default:
      return state
  }
}

export function ActivityProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE)
  // A ref, not state: registration happens in an effect and must not cause
  // a render of its own — the fallback pollers read it when they wake up.
  const liveSourcesRef = useRef(new Set())
  const [liveVersion, bumpLive] = useReducer((n) => n + 1, 0)

  const publish = useCallback((feature, entry) => {
    dispatch({ type: 'PUBLISH', feature, entry })
  }, [])

  const acknowledge = useCallback((feature) => {
    dispatch({ type: 'ACKNOWLEDGE', feature })
  }, [])

  /**
   * A mounted feature page claiming to be the live source for its feature.
   *
   * While one is registered the background source stops polling that
   * feature and simply relays what the page publishes.
   */
  const registerLiveSource = useCallback((feature) => {
    liveSourcesRef.current.add(feature)
    bumpLive()
    return () => {
      liveSourcesRef.current.delete(feature)
      bumpLive()
    }
  }, [])

  const hasLiveSource = useCallback((feature) => liveSourcesRef.current.has(feature), [])

  const value = useMemo(
    () => ({
      activities: state.activities,
      publish,
      acknowledge,
      registerLiveSource,
      hasLiveSource,
      liveVersion,
    }),
    [state.activities, publish, acknowledge, registerLiveSource, hasLiveSource, liveVersion]
  )

  return <ActivityContext.Provider value={value}>{children}</ActivityContext.Provider>
}

/**
 * Activity access that tolerates the provider being absent.
 *
 * Feature pages render in tests and in isolated stories without the shell
 * around them; publishing into a missing store is a no-op, not a crash.
 */
const NULL_ACTIVITY = {
  activities: INITIAL_STATE.activities,
  publish: () => {},
  acknowledge: () => {},
  registerLiveSource: () => () => {},
  hasLiveSource: () => false,
  liveVersion: 0,
}

export function useActivity() {
  return useContext(ActivityContext) || NULL_ACTIVITY
}

export function useFeatureActivity(feature) {
  return useActivity().activities[feature] || IDLE_ACTIVITY
}

/** Claim ownership of a feature's polling while this component is mounted. */
export function useLiveActivitySource(feature, enabled = true) {
  const { registerLiveSource } = useActivity()
  useEffect(() => {
    if (!enabled) return undefined
    return registerLiveSource(feature)
  }, [feature, enabled, registerLiveSource])
}
