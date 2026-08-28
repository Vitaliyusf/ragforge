/**
 * Opening a feature is what clears its marker.
 *
 * Exercised through the real shell: the acknowledgement policy is only
 * worth anything if it is wired to actual navigation.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/context/ThemeContext', () => ({
  useTheme: () => ({ resolvedTheme: 'dark', toggleTheme: vi.fn() }),
}))
vi.mock('@/features/auth', () => ({
  useAuth: () => ({ user: { email: 'admin@example.com' }, isAdmin: true, logout: vi.fn() }),
}))
vi.mock('@/features/config', () => ({
  configService: { getConfig: vi.fn().mockResolvedValue({}) },
}))
vi.mock('@/features/models', () => ({
  modelService: { getImplementations: vi.fn().mockResolvedValue({ implementations: [] }) },
}))
vi.mock('@/features/eval/components/EvalTab', () => ({ default: () => <div>eval workspace</div> }))

import TabbedPageLayout from './TabbedPageLayout'
import { ACTIVITY_FEATURES, ACTIVITY_STATES } from '@/features/activity/activityModel'
import { ActivityProvider, useActivity } from '@/features/activity/ActivityContext'

function Publisher({ entry }) {
  const { publish } = useActivity()
  publish(ACTIVITY_FEATURES.EVAL, entry)
  return null
}

afterEach(() => vi.clearAllMocks())

describe('acknowledgement on navigation', () => {
  it('clears an unseen terminal Eval marker when Eval is opened', async () => {
    const user = userEvent.setup()
    render(
      <ActivityProvider>
        <Publisher entry={{ state: ACTIVITY_STATES.SUCCESS, label: 'Regular E2E' }} />
        <TabbedPageLayout defaultTab="chat" />
      </ActivityProvider>
    )

    const marked = await screen.findByRole('button', { name: /^Eval — benchmark completed/ })
    await user.click(marked)
    expect(await screen.findByRole('button', { name: 'Eval' })).toBeInTheDocument()
  })

  it('leaves a running Eval marker alone when Eval is opened', async () => {
    const user = userEvent.setup()
    render(
      <ActivityProvider>
        <Publisher entry={{ state: ACTIVITY_STATES.RUNNING, label: 'Regular E2E' }} />
        <TabbedPageLayout defaultTab="chat" />
      </ActivityProvider>
    )

    await user.click(await screen.findByRole('button', { name: /benchmark running/ }))
    expect(await screen.findByRole('button', { name: /benchmark running/ })).toBeInTheDocument()
  })
})
