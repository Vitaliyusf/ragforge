/**
 * The nav indicator itself: what it says, what it draws, and what it never
 * does — move the layout, blink, or rely on colour alone.
 */
import { render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/context/ThemeContext', () => ({
  useTheme: () => ({ resolvedTheme: 'dark', toggleTheme: vi.fn() }),
}))
vi.mock('@/features/auth', () => ({
  useAuth: () => ({
    user: { email: 'admin@example.com', role: 'admin' },
    isAdmin: true,
    logout: vi.fn(),
  }),
}))
vi.mock('@/features/config', () => ({
  configService: { getConfig: vi.fn().mockResolvedValue({}) },
}))
vi.mock('@/features/models', () => ({
  modelService: { getImplementations: vi.fn().mockResolvedValue({ implementations: [] }) },
}))

import Header from './Header'
import { ACTIVITY_FEATURES, ACTIVITY_STATES } from '@/features/activity/activityModel'
import { ActivityProvider, useActivity } from '@/features/activity/ActivityContext'

/** Publishes one entry, then renders the real header against it. */
function Publisher({ feature, entry }) {
  const { publish } = useActivity()
  publish(feature, entry)
  return null
}

function renderHeader({ feature = ACTIVITY_FEATURES.EVAL, entry, activeTab = 'chat' } = {}) {
  return render(
    <ActivityProvider>
      {entry ? <Publisher feature={feature} entry={entry} /> : null}
      <Header activeTab={activeTab} setActiveTab={vi.fn()} />
    </ActivityProvider>
  )
}

const setReducedMotion = (matches) => {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    matches,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

beforeEach(() => setReducedMotion(false))
afterEach(() => vi.clearAllMocks())

describe('navigation activity indicators', () => {
  it('gives a running item accessible status text, not just a dot', () => {
    renderHeader({
      entry: {
        state: ACTIVITY_STATES.RUNNING,
        label: 'Regular E2E',
        progress: { completed: 18, total: 30 },
      },
    })
    const item = screen.getByRole('button', { name: 'Eval — benchmark running · 18/30 · Regular E2E' })
    expect(item).toHaveAttribute('title', 'Eval — benchmark running · 18/30 · Regular E2E')
    expect(within(item).getByRole('status')).toHaveTextContent('benchmark running')
  })

  it('leaves an idle item exactly as it was', () => {
    renderHeader()
    const item = screen.getByRole('button', { name: 'Eval' })
    expect(item).not.toHaveAttribute('title')
    expect(item.querySelector('[data-testid="nav-activity-mark"]')).toBeNull()
    expect(item.querySelector('[data-testid="nav-activity-rail"]')).toBeNull()
  })

  it('never reduces a terminal state to colour alone', () => {
    for (const state of [ACTIVITY_STATES.SUCCESS, ACTIVITY_STATES.WARNING, ACTIVITY_STATES.FAILED]) {
      const view = renderHeader({ entry: { state } })
      const item = screen.getByRole('button', { name: new RegExp('^Eval — ') })
      const mark = item.querySelector('[data-testid="nav-activity-mark"]')
      expect(mark).toHaveAttribute('data-state', state)
      // A shape as well as a colour, plus the status text on the item.
      expect(mark.querySelector('svg')).not.toBeNull()
      expect(within(item).getByRole('status').textContent.length).toBeGreaterThan(0)
      view.unmount()
    }
  })

  it('distinguishes warning from failure', () => {
    // Scoped to the nav item: the global activity control carries a status of
    // its own, and the point here is what the *item* says.
    const statusOfEvalItem = () =>
      within(screen.getByRole('button', { name: /^Eval — / })).getByRole('status').textContent

    const warning = renderHeader({ entry: { state: ACTIVITY_STATES.WARNING } })
    const warningText = statusOfEvalItem()
    warning.unmount()
    renderHeader({ entry: { state: ACTIVITY_STATES.FAILED } })
    expect(statusOfEvalItem()).not.toBe(warningText)
  })

  it('drops the moving rail under reduced motion but keeps the status', () => {
    setReducedMotion(true)
    renderHeader({ entry: { state: ACTIVITY_STATES.RUNNING } })
    const item = screen.getByRole('button', { name: /benchmark running/ })
    expect(item.querySelector('[data-testid="nav-activity-rail"]')).toBeNull()
    expect(item.querySelector('[data-testid="nav-activity-rail-static"]')).not.toBeNull()
    expect(item.querySelector('.activity-mark--breathe')).toBeNull()
    expect(item.querySelector('.activity-mark--static')).not.toBeNull()
  })

  it('keeps the nav geometry and the focus ring identical as activity changes', () => {
    const idle = renderHeader()
    const idleItem = screen.getByRole('button', { name: 'Eval' })
    const idleSlots = idleItem.querySelectorAll('.activity-slot').length
    const idleClasses = idleItem.className
    idle.unmount()

    renderHeader({ entry: { state: ACTIVITY_STATES.RUNNING } })
    const runningItem = screen.getByRole('button', { name: /benchmark running/ })
    // The slot is reserved in both states, and the item's own classes — the
    // ones that size it and draw its focus ring — do not change.
    expect(runningItem.querySelectorAll('.activity-slot').length).toBe(idleSlots)
    expect(idleSlots).toBe(1)
    expect(runningItem.className).toBe(idleClasses)
    expect(runningItem.className).toContain('focus-visible:ring-2')
    runningItem.focus()
    expect(runningItem).toHaveFocus()
  })
})
