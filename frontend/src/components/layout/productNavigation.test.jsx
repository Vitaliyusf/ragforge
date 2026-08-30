/**
 * PRODUCT-01 — the header as the product model renders it.
 *
 * Three things have to be true on screen, not just in the model: the pillars
 * are announced as groups, a member never sees an operator's destinations,
 * and there is exactly one control saying whether anything is happening.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

const { authState } = vi.hoisted(() => ({
  authState: { user: { email: 'admin@example.com', role: 'admin' }, isAdmin: true },
}))

vi.mock('@/context/ThemeContext', () => ({
  useTheme: () => ({ resolvedTheme: 'dark', toggleTheme: vi.fn() }),
}))
vi.mock('@/features/auth', () => ({
  useAuth: () => ({ ...authState, logout: vi.fn() }),
}))
vi.mock('@/features/config', () => ({
  configService: { getConfig: vi.fn().mockResolvedValue({}) },
}))

import Header from './Header'
import { ACTIVITY_FEATURES, ACTIVITY_STATES } from '@/features/activity/activityModel'
import { ActivityProvider, useActivity } from '@/features/activity/ActivityContext'

function Publisher({ entries }) {
  const { publish } = useActivity()
  for (const [feature, entry] of Object.entries(entries)) publish(feature, entry)
  return null
}

function renderHeader({ role = 'admin', entries = null, activeTab = 'chat' } = {}) {
  authState.user = { email: `${role}@example.com`, role }
  authState.isAdmin = role === 'admin'
  return render(
    <ActivityProvider>
      {entries ? <Publisher entries={entries} /> : null}
      <Header activeTab={activeTab} setActiveTab={vi.fn()} />
    </ActivityProvider>
  )
}

const groupNames = () =>
  screen
    .getAllByRole('group')
    .map((group) => group.getAttribute('aria-label'))

const itemsIn = (pillar) =>
  [...screen.getByRole('group', { name: pillar }).querySelectorAll('button')].map((button) =>
    button.getAttribute('data-destination')
  )

afterEach(() => {
  authState.user = { email: 'admin@example.com', role: 'admin' }
  authState.isAdmin = true
})

describe('pillared navigation', () => {
  it('announces the four pillars as named groups', () => {
    renderHeader()
    expect(groupNames()).toEqual(['Workspace', 'Quality', 'Operations', 'Administration'])
  })

  it('puts each destination under the pillar that owns it', () => {
    renderHeader()
    expect(itemsIn('Workspace')).toEqual(['chat', 'files', 'memory'])
    expect(itemsIn('Quality')).toEqual(['eval', 'metrics'])
    expect(itemsIn('Operations')).toEqual(['models', 'logs', 'health'])
    expect(itemsIn('Administration')).toEqual(['users', 'config'])
  })

  it('calls the document destination Knowledge, once', () => {
    renderHeader()
    expect(screen.getByRole('button', { name: 'Knowledge' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Files' })).not.toBeInTheDocument()
  })

  it('marks the open destination as the current page', () => {
    renderHeader({ activeTab: 'eval' })
    expect(screen.getByRole('button', { name: 'Eval' })).toHaveAttribute('aria-current', 'page')
  })
})

describe('role-aware visibility', () => {
  it('shows a member only the Workspace pillar', () => {
    renderHeader({ role: 'user' })
    expect(groupNames()).toEqual(['Workspace'])
    expect(itemsIn('Workspace')).toEqual(['chat', 'upload', 'memory'])
  })

  it('never renders an operations or administration destination for a member', () => {
    renderHeader({ role: 'user' })
    for (const name of ['Logs', 'Health', 'Models', 'Users', 'Settings', 'Metrics', 'Eval']) {
      expect(screen.queryByRole('button', { name })).not.toBeInTheDocument()
    }
  })
})

describe('one global activity control', () => {
  it('says Ready when nothing is running', () => {
    renderHeader()
    expect(screen.getByTestId('global-activity')).toHaveAccessibleName(
      'Workspace activity: Ready'
    )
  })

  it('counts active work instead of a permanently lit dot', () => {
    renderHeader({
      entries: {
        [ACTIVITY_FEATURES.CHAT]: { state: ACTIVITY_STATES.RUNNING },
        [ACTIVITY_FEATURES.EVAL]: { state: ACTIVITY_STATES.RUNNING },
      },
    })
    const control = screen.getByTestId('global-activity')
    expect(control).toHaveTextContent('2 active')
    expect(screen.getByTestId('logo-activity-dot')).toHaveAttribute(
      'data-activity-state',
      'active'
    )
  })

  it('reports degradation as text, never as colour alone', () => {
    renderHeader({ entries: { [ACTIVITY_FEATURES.EVAL]: { state: ACTIVITY_STATES.FAILED } } })
    const control = screen.getByTestId('global-activity')
    expect(control).toHaveTextContent('Degraded')
    // An icon accompanies the word, so the state survives without colour.
    expect(control.querySelector('svg')).not.toBeNull()
  })

  it('lists the real work in its popover', async () => {
    const user = userEvent.setup()
    renderHeader({
      entries: {
        [ACTIVITY_FEATURES.EVAL]: {
          state: ACTIVITY_STATES.RUNNING,
          progress: { completed: 2, total: 8 },
        },
      },
    })
    await user.click(screen.getByTestId('global-activity'))
    const panel = screen.getByRole('list')
    expect(within(panel).getByText('Evaluation')).toBeInTheDocument()
    expect(within(panel).getByText('Eval · 2/8')).toBeInTheDocument()
    expect(within(panel).getByText('Running')).toBeInTheDocument()
  })

  it('says so plainly when there is nothing to show', async () => {
    const user = userEvent.setup()
    renderHeader()
    await user.click(screen.getByTestId('global-activity'))
    expect(screen.getByText('No background work is running.')).toBeInTheDocument()
    expect(screen.queryByRole('list')).not.toBeInTheDocument()
  })

  it('is the only global liveness claim in the header', () => {
    renderHeader({ entries: { [ACTIVITY_FEATURES.CHAT]: { state: ACTIVITY_STATES.RUNNING } } })
    expect(screen.getAllByTestId('global-activity')).toHaveLength(1)
    expect(screen.queryByText(/^Live$/)).not.toBeInTheDocument()
  })
})
