/**
 * The navigation model: pillars, role visibility, and the guarantee that the
 * header and the shell cannot disagree about what exists.
 */
import { describe, expect, it } from 'vitest'

import {
  DESTINATIONS,
  FALLBACK_TAB,
  NAV_PILLARS,
  PILLAR_ORDER,
  ROLE_PILLARS,
  allowedTabsForRole,
  destinationLabel,
  destinationsForRole,
  navigationForRole,
} from './navigationModel'

const ids = (groups) => groups.flatMap((group) => group.items.map((item) => item.id))

describe('pillars', () => {
  it('groups every destination under one of the four product pillars', () => {
    for (const destination of DESTINATIONS) {
      expect(PILLAR_ORDER).toContain(destination.pillar)
    }
  })

  it('renders pillars in product order, workspace first', () => {
    const groups = navigationForRole('admin')
    expect(groups.map((group) => group.pillar)).toEqual(PILLAR_ORDER)
    expect(groups[0].label).toBe('Workspace')
  })

  it('puts the daily work in Workspace and the subsystems below it', () => {
    const groups = navigationForRole('admin')
    const byPillar = Object.fromEntries(
      groups.map((group) => [group.pillar, group.items.map((item) => item.id)])
    )
    expect(byPillar[NAV_PILLARS.WORKSPACE]).toContain('chat')
    expect(byPillar[NAV_PILLARS.WORKSPACE]).toContain('files')
    expect(byPillar[NAV_PILLARS.QUALITY]).toEqual(['eval', 'metrics'])
    expect(byPillar[NAV_PILLARS.OPERATIONS]).toEqual(['models', 'logs', 'health'])
    expect(byPillar[NAV_PILLARS.ADMINISTRATION]).toEqual(['users', 'config'])
  })

  it('never emits a headed group with nothing under it', () => {
    for (const role of Object.keys(ROLE_PILLARS)) {
      for (const group of navigationForRole(role)) {
        expect(group.items.length).toBeGreaterThan(0)
      }
    }
  })
})

describe('role visibility', () => {
  it('shows a member only their own workspace', () => {
    const groups = navigationForRole('user')
    expect(groups.map((group) => group.pillar)).toEqual([NAV_PILLARS.WORKSPACE])
    expect(ids(groups)).toEqual(['chat', 'upload', 'memory'])
  })

  it('never shows a member an operations or administration destination', () => {
    const visible = allowedTabsForRole('user')
    for (const id of ['logs', 'health', 'models', 'users', 'config', 'metrics', 'eval']) {
      expect(visible.has(id)).toBe(false)
    }
  })

  it('widens with the role rather than replacing what came before', () => {
    const member = allowedTabsForRole('member')
    const evaluator = allowedTabsForRole('evaluator')
    const operator = allowedTabsForRole('operator')
    const admin = allowedTabsForRole('admin')

    for (const id of member) expect(evaluator.has(id) || id === 'upload').toBe(true)
    for (const id of evaluator) expect(operator.has(id)).toBe(true)
    for (const id of operator) expect(admin.has(id)).toBe(true)
    expect(admin.has('users')).toBe(true)
    expect(operator.has('users')).toBe(false)
  })

  it('treats an unrecognised role as the least-privileged one', () => {
    // A role the gateway does not issue must not fall through to "sees
    // everything" — nor to an empty shell with no way to reach Chat.
    expect(ids(navigationForRole('wizard'))).toEqual(ids(navigationForRole('user')))
    expect(ids(navigationForRole(undefined))).toEqual(ids(navigationForRole('user')))
  })

  it('always leaves the fallback destination reachable', () => {
    for (const role of [...Object.keys(ROLE_PILLARS), 'wizard', null]) {
      expect(allowedTabsForRole(role).has(FALLBACK_TAB)).toBe(true)
    }
  })
})

describe('feature-flagged destinations', () => {
  it('omits Training unless the flag is on', () => {
    expect(allowedTabsForRole('admin').has('training')).toBe(false)
    expect(allowedTabsForRole('admin', { features: { training: true } }).has('training')).toBe(true)
  })
})

describe('one model, two readers', () => {
  it('lists exactly the destinations the shell will open', () => {
    for (const role of Object.keys(ROLE_PILLARS)) {
      const shown = ids(navigationForRole(role)).sort()
      const openable = [...allowedTabsForRole(role)].sort()
      expect(shown).toEqual(openable)
    }
  })

  it('gives each destination one canonical label', () => {
    expect(destinationLabel('files')).toBe('Knowledge')
    expect(destinationLabel('config')).toBe('Settings')
    const labels = destinationsForRole('admin', { features: { training: true } }).map(
      (destination) => destination.label
    )
    expect(new Set(labels).size).toBe(labels.length)
  })
})
