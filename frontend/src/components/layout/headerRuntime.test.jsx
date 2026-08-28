/**
 * Header runtime-architecture tests (REACT-19-01).
 *
 * Connectivity is read through `useSyncExternalStore` instead of being copied
 * into component state by an Effect, and the settings-popover dismissal
 * listeners are mounted only while the popover is open rather than for the
 * whole session.
 */
import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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

import Header from './Header'
import { ActivityProvider } from '@/features/activity/ActivityContext'

function renderHeader() {
  return render(
    <ActivityProvider>
      <Header activeTab="chat" setActiveTab={vi.fn()} />
    </ActivityProvider>
  )
}

const setOnline = (value) => {
  Object.defineProperty(navigator, 'onLine', { configurable: true, value })
}

const dismissalCalls = (spy) =>
  spy.mock.calls.filter(([event]) => event === 'mousedown' || event === 'keydown')

describe('Header runtime', () => {
  afterEach(() => {
    setOnline(true)
  })

  it('tracks connectivity from the browser rather than a mirrored state copy', async () => {
    setOnline(true)
    renderHeader()
    expect(screen.queryByText(/offline/i)).not.toBeInTheDocument()

    setOnline(false)
    await act(async () => { window.dispatchEvent(new Event('offline')) })
    expect(screen.getByText(/offline/i)).toBeInTheDocument()

    setOnline(true)
    await act(async () => { window.dispatchEvent(new Event('online')) })
    expect(screen.queryByText(/offline/i)).not.toBeInTheDocument()
  })

  it('attaches dismissal listeners only while the settings popover is open', async () => {
    const addSpy = vi.spyOn(document, 'addEventListener')
    const removeSpy = vi.spyOn(document, 'removeEventListener')
    try {
      renderHeader()
      expect(dismissalCalls(addSpy)).toHaveLength(0)

      await userEvent.click(screen.getByRole('button', { name: /settings/i }))
      expect(dismissalCalls(addSpy)).toHaveLength(2)
      expect(dismissalCalls(removeSpy)).toHaveLength(0)

      await userEvent.keyboard('{Escape}')
      expect(dismissalCalls(removeSpy)).toHaveLength(2)
    } finally {
      addSpy.mockRestore()
      removeSpy.mockRestore()
    }
  })
})
