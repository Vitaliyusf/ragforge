'use client'

/**
 * The activity mark on a navigation item.
 *
 * It reads as a build indicator rather than a spinner: a small dot with a
 * soft halo while work runs, a thin rail under the item, and a single
 * micro-animation when the work ends. The slot has a fixed width and the
 * rail is absolutely positioned, so a tab that starts working does not move
 * its neighbours by a pixel.
 */

import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Check, X } from 'lucide-react'
import { ACTIVITY_STATES, isTerminalState } from '../activityModel'
import { usePrefersReducedMotion } from '@/lib/accessibility/usePrefersReducedMotion'

const STATE_COLORS = {
  [ACTIVITY_STATES.QUEUED]: 'var(--accent)',
  [ACTIVITY_STATES.RUNNING]: 'var(--accent)',
  [ACTIVITY_STATES.SUCCESS]: 'var(--success)',
  [ACTIVITY_STATES.WARNING]: 'var(--warning)',
  [ACTIVITY_STATES.FAILED]: 'var(--danger)',
}

/* Colour is never the only cue: every terminal state also carries a shape. */
const STATE_ICONS = {
  [ACTIVITY_STATES.SUCCESS]: Check,
  [ACTIVITY_STATES.WARNING]: AlertTriangle,
  [ACTIVITY_STATES.FAILED]: X,
}

export default function NavActivityIndicator({ state, selected = false, animateEntry = true }) {
  const reducedMotion = usePrefersReducedMotion()
  const [emphasize, setEmphasize] = useState(false)
  const previousState = useRef(state)

  // One pop when the state becomes terminal — never a repeating animation.
  useEffect(() => {
    const changed = previousState.current !== state
    previousState.current = state
    if (!changed || !animateEntry || reducedMotion) return undefined
    if (!isTerminalState(state)) return undefined
    setEmphasize(true)
    const timer = setTimeout(() => setEmphasize(false), 900)
    return () => clearTimeout(timer)
  }, [state, animateEntry, reducedMotion])

  const color = STATE_COLORS[state]
  const Icon = STATE_ICONS[state]
  const running = state === ACTIVITY_STATES.RUNNING || state === ACTIVITY_STATES.QUEUED
  const popClass = emphasize
    ? state === ACTIVITY_STATES.FAILED
      ? ' activity-mark--emphasis'
      : ' activity-mark--pop'
    : ''

  return (
    <>
      {/* Always rendered, always the same size: the slot reserves its space
          whether or not anything is happening. */}
      <span aria-hidden="true" className="activity-slot">
        {color && (
          <span
            className={
              'activity-mark' +
              (running ? (reducedMotion ? ' activity-mark--static' : ' activity-mark--breathe') : '') +
              (selected ? ' activity-mark--selected' : '') +
              popClass
            }
            style={{ color, background: Icon ? 'transparent' : color }}
            data-state={state}
            data-testid="nav-activity-mark"
          >
            {Icon ? <Icon size={9} strokeWidth={3.2} /> : null}
          </span>
        )}
      </span>

      {running && !reducedMotion && (
        <span
          aria-hidden="true"
          data-testid="nav-activity-rail"
          className={'activity-rail' + (selected ? ' activity-rail--selected' : '')}
        />
      )}
      {running && reducedMotion && (
        <span
          aria-hidden="true"
          data-testid="nav-activity-rail-static"
          className="activity-rail activity-rail--static"
        />
      )}
    </>
  )
}
