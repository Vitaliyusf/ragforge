/**
 * OBS-UX-01 — a deep link arriving at its destination.
 *
 * The builders and the executor are unit-tested elsewhere. What this covers
 * is the seam between them and the shell: following a link has to switch the
 * workspace *and* deliver the reason, or the operator lands on an unfiltered
 * page and has to re-type what they just clicked.
 */
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/',
}))
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

vi.mock('@/features/chat/components/ChatTab', async () => {
  const { default: DeepLink } = await import('@/components/observability/DeepLink')
  const { documentLink, logsLinkForService } = await import('@/lib/observability/deepLinks')
  return {
    default: function ChatTabStub() {
      return (
        <div>
          <span>chat workspace</span>
          <DeepLink link={documentLink('file-7', 'report.pdf')} />
          <DeepLink link={logsLinkForService('rag')} />
        </div>
      )
    },
  }
})

vi.mock('@/features/files/components/FilesTab', () => ({
  default: function FilesTabStub({ intent }) {
    return <div>knowledge workspace filtered to {intent?.query ?? 'nothing'}</div>
  },
}))

vi.mock('@/features/logs/components/LogsTab', () => ({
  default: function LogsTabStub() {
    return <div>logs workspace</div>
  },
}))

import TabbedPageLayout from './TabbedPageLayout'
import { ActivityProvider } from '@/features/activity/ActivityContext'
import { renderWithProviders } from '@/test/render'

function renderShell() {
  return renderWithProviders(
    <ActivityProvider>
      <TabbedPageLayout defaultTab="chat" />
    </ActivityProvider>
  )
}

describe('following a deep link through the shell', () => {
  it('opens the document library already narrowed to the file that was asked about', async () => {
    const user = userEvent.setup()
    renderShell()

    await user.click(await screen.findByRole('button', { name: /Open in Knowledge/i }))

    expect(
      await screen.findByText('knowledge workspace filtered to file-7')
    ).toBeInTheDocument()
  })

  it('sets the log filters before the log workspace is on screen', async () => {
    const user = userEvent.setup()
    const { store } = renderShell()

    await user.click(await screen.findByRole('button', { name: /View Logs/i }))

    expect(await screen.findByText('logs workspace')).toBeInTheDocument()
    expect(store.getState().logs.selectedServices).toEqual(['rag'])
    expect(store.getState().logs.severityFilter).toEqual(['error', 'warning'])
  })
})
