/**
 * Tests for Eval's promotion out of Metrics.
 *
 * Three things have to hold together: Eval is a primary destination, Metrics
 * no longer offers it as a sub-tab, and anything still pointing at the old
 * Metrics sub-tab lands on the new workspace instead of a dead page.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

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
  configService: {
    getConfig: vi.fn().mockResolvedValue({}),
  },
}))
vi.mock('@/features/models', () => ({
  modelService: { getImplementations: vi.fn().mockResolvedValue({ implementations: [] }) },
}))

const { mockUseMetrics } = vi.hoisted(() => ({ mockUseMetrics: vi.fn() }))
vi.mock('@/features/metrics/hooks/useMetrics', () => ({ useMetrics: mockUseMetrics }))
mockUseMetrics.mockReturnValue({
  data: null,
  loading: false,
  error: null,
  promAvailable: true,
  lastUpdated: null,
  refresh: vi.fn(),
})

import Header from './Header'
import { LEGACY_TAB_ALIASES, resolveTab } from './TabbedPageLayout'
import MetricsTab from '@/features/metrics/components/MetricsTab'

describe('primary navigation', () => {
  it('offers Eval as a top-level destination', async () => {
    const user = userEvent.setup()
    const setActiveTab = vi.fn()
    render(<Header activeTab="chat" setActiveTab={setActiveTab} />)

    const evalTab = screen.getByRole('button', { name: 'Eval' })
    await user.click(evalTab)
    expect(setActiveTab).toHaveBeenCalledWith('eval')
  })

  it('opens the Quality pillar, ahead of the operational destinations', () => {
    render(<Header activeTab="eval" setActiveTab={vi.fn()} />)
    const quality = screen.getByRole('group', { name: 'Quality' })
    const labels = [...quality.querySelectorAll('button')].map((button) =>
      button.getAttribute('aria-label')
    )
    expect(labels[0]).toBe('Eval')

    const nav = screen.getByRole('navigation', { name: 'Main navigation' })
    const groups = [...nav.querySelectorAll('[role="group"]')].map((group) =>
      group.getAttribute('aria-label')
    )
    expect(groups.indexOf('Quality')).toBeLessThan(groups.indexOf('Operations'))
  })

  it('marks Eval as the current page when it is selected', () => {
    render(<Header activeTab="eval" setActiveTab={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Eval' })).toHaveAttribute('aria-current', 'page')
  })
})

describe('metrics sub-navigation', () => {
  it('no longer renders Eval as a metrics section', () => {
    render(<MetricsTab />)
    expect(screen.getByRole('heading', { name: 'Metrics' })).toBeInTheDocument()
    for (const label of ['Overview', 'Latency', 'Retrieval', 'Quality', 'Pipeline']) {
      expect(screen.getByRole('button', { name: new RegExp(label, 'i') })).toBeInTheDocument()
    }
    expect(screen.queryByRole('button', { name: /^Eval$/i })).not.toBeInTheDocument()
  })

  it('sends a request for the old Eval section to the Eval workspace', () => {
    const onNavigate = vi.fn()
    render(<MetricsTab section="eval" onNavigate={onNavigate} />)
    expect(onNavigate).toHaveBeenCalledWith('eval')
    // And does not leave a dead page behind while the shell switches.
    expect(screen.getByRole('heading', { name: 'Metrics' })).toBeInTheDocument()
  })

  it('keeps its own sections working when one is requested by name', () => {
    render(<MetricsTab section="latency" />)
    expect(mockUseMetrics).toHaveBeenLastCalledWith('latency', expect.any(Object))
  })
})

describe('legacy destinations', () => {
  it('resolves the old Metrics Eval links to the Eval workspace', () => {
    for (const alias of Object.keys(LEGACY_TAB_ALIASES)) {
      expect(resolveTab(alias)).toBe('eval')
    }
  })

  it('leaves every other destination untouched', () => {
    expect(resolveTab('metrics')).toBe('metrics')
    expect(resolveTab('chat')).toBe('chat')
  })
})
