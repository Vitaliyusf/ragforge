/**
 * Application-shell contracts for NEXT-16-01.
 *
 * The shell is the thing that must not blink: navigating between workspaces
 * keeps the chrome mounted, keeps hand-entered state on the surfaces that are
 * expensive to rebuild, and still stops the work of a workspace nobody is
 * looking at.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mockProbe = {
  filesEffects: 0,
  filesCleanups: 0,
  logsMounts: 0,
}

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

vi.mock('@/features/chat/components/ChatTab', () => ({
  default: () => <div>chat workspace</div>,
}))

vi.mock('@/features/files/components/FilesTab', async () => {
  const { useEffect, useState } = await import('react')
  return {
    default: function FilesTabStub() {
      const [query, setQuery] = useState('')
      useEffect(() => {
        mockProbe.filesEffects += 1
        return () => {
          mockProbe.filesCleanups += 1
        }
      }, [])
      return (
        <div>
          <span>files workspace</span>
          <input
            aria-label="files search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
      )
    },
  }
})

vi.mock('@/features/logs/components/LogsTab', async () => {
  const { useEffect, useState } = await import('react')
  return {
    default: function LogsTabStub() {
      const [filter, setFilter] = useState('')
      useEffect(() => {
        mockProbe.logsMounts += 1
      }, [])
      return (
        <div>
          <span>logs workspace</span>
          <input
            aria-label="logs filter"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          />
        </div>
      )
    },
  }
})

vi.mock('@/features/config/components/ConfigTab', () => ({
  default: () => <div>settings workspace</div>,
}))

import TabbedPageLayout from './TabbedPageLayout'
import { ActivityProvider } from '@/features/activity/ActivityContext'

function renderShell(props = {}) {
  return render(
    <ActivityProvider>
      <TabbedPageLayout defaultTab="chat" {...props} />
    </ActivityProvider>
  )
}

beforeEach(() => {
  mockProbe.filesEffects = 0
  mockProbe.filesCleanups = 0
  mockProbe.logsMounts = 0
})

afterEach(() => vi.clearAllMocks())

describe('workspace state preservation', () => {
  it('keeps hand-entered Files state when the operator visits another workspace', async () => {
    const user = userEvent.setup()
    renderShell()

    await user.click(screen.getByRole('button', { name: 'Knowledge' }))
    await user.type(await screen.findByLabelText('files search'), 'invoice')

    await user.click(screen.getByRole('button', { name: 'Logs' }))
    await screen.findByText('logs workspace')

    await user.click(screen.getByRole('button', { name: 'Knowledge' }))
    expect(await screen.findByLabelText('files search')).toHaveValue('invoice')
  })

  it('rebuilds a non-retained workspace instead of paying to keep it alive', async () => {
    const user = userEvent.setup()
    renderShell()

    await user.click(screen.getByRole('button', { name: 'Logs' }))
    await user.type(await screen.findByLabelText('logs filter'), 'gateway')

    await user.click(screen.getByRole('button', { name: 'Chat' }))
    await screen.findByText('chat workspace')

    await user.click(screen.getByRole('button', { name: 'Logs' }))
    expect(await screen.findByLabelText('logs filter')).toHaveValue('')
    expect(mockProbe.logsMounts).toBe(2)
  })
})

describe('hidden workspace lifecycle', () => {
  it('stops a retained workspace when it is hidden and resumes it exactly once', async () => {
    const user = userEvent.setup()
    renderShell()

    await user.click(screen.getByRole('button', { name: 'Knowledge' }))
    await screen.findByLabelText('files search')
    expect(mockProbe.filesEffects).toBe(1)
    expect(mockProbe.filesCleanups).toBe(0)

    await user.click(screen.getByRole('button', { name: 'Logs' }))
    await screen.findByText('logs workspace')
    expect(mockProbe.filesCleanups).toBe(1)

    await user.click(screen.getByRole('button', { name: 'Knowledge' }))
    await screen.findByLabelText('files search')
    expect(mockProbe.filesEffects).toBe(2)
  })
})

describe('route-named destinations', () => {
  it('opens the destination a URL names without rebuilding the shell', async () => {
    const { rerender } = renderShell({ routeTab: 'chat' })
    const nav = await screen.findByRole('navigation', { name: 'Main navigation' })
    await screen.findByText('chat workspace')

    rerender(
      <ActivityProvider>
        <TabbedPageLayout defaultTab="chat" routeTab="config" />
      </ActivityProvider>
    )

    expect(await screen.findByText('settings workspace')).toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBe(nav)
  })

  it('leaves a hand-picked tab alone while the route stands still', async () => {
    const user = userEvent.setup()
    const { rerender } = renderShell({ routeTab: 'chat' })

    await user.click(screen.getByRole('button', { name: 'Logs' }))
    await screen.findByText('logs workspace')

    rerender(
      <ActivityProvider>
        <TabbedPageLayout defaultTab="chat" routeTab="chat" />
      </ActivityProvider>
    )

    expect(screen.getByText('logs workspace')).toBeInTheDocument()
  })
})
