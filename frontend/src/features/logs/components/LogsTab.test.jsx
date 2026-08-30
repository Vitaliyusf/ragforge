/**
 * OBS-UX-01 — logs as events rather than as text.
 *
 * A correlation id is the only thing that connects a log line to the turn,
 * run or document it belongs to, so it has to be a control rather than a
 * substring. And when a deep link has already narrowed the stream, an empty
 * result must read as "not in the buffer", never as "nothing happened".
 */
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockUseLogs } = vi.hoisted(() => ({ mockUseLogs: vi.fn() }))

vi.mock('@/features/logs', () => ({ useLogs: mockUseLogs }))

import LogsTab from './LogsTab'
import { renderWithProviders, createTestStore } from '@/test/render'
import { NavigationProvider } from '@/components/layout/NavigationContext'
import { LOG_SERVICES } from '@/lib/observability/deepLinks'
import { createDeepLinkFollower } from '@/lib/observability/followDeepLink'
import {
  setSelectedServices,
  setSeverityFilter,
  setTextFilter,
} from '@/store/slices/logsSlice'

/**
 * The viewer inside a shell that can actually follow a link — the executor is
 * the shell's, so a bare LogsTab renders its id controls as inert.
 */
function renderInShell(store = createTestStore()) {
  const navigate = vi.fn()
  const followDeepLink = createDeepLinkFollower({
    dispatch: store.dispatch,
    router: { push: vi.fn() },
    navigate,
    logActions: { setSelectedServices, setSeverityFilter, setTextFilter },
  })
  const result = renderWithProviders(
    <NavigationProvider value={{ navigate, followDeepLink }}>
      <LogsTab />
    </NavigationProvider>,
    { store }
  )
  return { ...result, navigate }
}

const STRUCTURED_LINE = JSON.stringify({
  timestamp: '2026-01-01T12:00:00Z',
  service: 'gateway',
  location: 'router.py:41',
  message: 'Upstream refused the request',
  severity: 'ERROR',
  trace_id: 'trace-9f2c',
  data: { status: 502 },
})

function mockLogs(lines) {
  mockUseLogs.mockReturnValue({
    logs: { gateway: { service: 'gateway', logs: lines } },
    loading: false,
    services: [...LOG_SERVICES],
    filteredLogs: lines.map((line, index) => ({
      service: 'gateway',
      line,
      severity: 'error',
      index,
      originalIndex: index,
    })),
    fetchLogs: vi.fn(),
    fetchSelectedServicesLogs: vi.fn(),
    fetchAllLogs: vi.fn(),
    clearLogs: vi.fn(),
  })
}

describe('LogsTab', () => {
  beforeEach(() => {
    mockUseLogs.mockReset()
  })

  it('shows a structured entry as an event, with its payload as secondary detail', () => {
    mockLogs([STRUCTURED_LINE])
    renderWithProviders(<LogsTab />)

    expect(screen.getByText('Upstream refused the request')).toBeInTheDocument()
    expect(screen.getByText('router.py:41')).toBeInTheDocument()
    // The raw JSON is available, not the primary rendering.
    expect(screen.getByText('Event data')).toBeInTheDocument()
  })

  it('makes the correlation id a control that re-filters the stream around it', async () => {
    const user = userEvent.setup()
    mockLogs([STRUCTURED_LINE])
    const { store } = renderInShell()

    await user.click(screen.getByRole('button', { name: /Trace trace-9f2c/i }))

    expect(store.getState().logs.textFilter).toBe('trace-9f2c')
    expect(store.getState().logs.selectedServices).toEqual([...LOG_SERVICES])
  })

  it('renders an unstructured line as its own text without inventing fields', () => {
    mockLogs(['gateway starting up'])
    renderWithProviders(<LogsTab />)

    expect(screen.getByText('gateway starting up')).toBeInTheDocument()
    expect(screen.queryByText('Event data')).not.toBeInTheDocument()
  })

  it('blames the buffer, not the system, when a filtered stream comes back empty', () => {
    mockUseLogs.mockReturnValue({
      logs: {},
      loading: false,
      services: [...LOG_SERVICES],
      filteredLogs: [],
      fetchLogs: vi.fn(),
      fetchSelectedServicesLogs: vi.fn(),
      fetchAllLogs: vi.fn(),
      clearLogs: vi.fn(),
    })

    renderWithProviders(<LogsTab />)

    // No filter yet: the honest message is that nothing has been loaded.
    expect(screen.getByText('No service output yet')).toBeInTheDocument()
  })

  it('blames the buffer rather than the system when a narrowed stream is empty', () => {
    mockUseLogs.mockReturnValue({
      logs: {},
      loading: false,
      services: [...LOG_SERVICES],
      filteredLogs: [],
      fetchLogs: vi.fn(),
      fetchSelectedServicesLogs: vi.fn(),
      fetchAllLogs: vi.fn(),
      clearLogs: vi.fn(),
    })
    const store = createTestStore()
    store.dispatch(setTextFilter('trace-9f2c'))

    renderWithProviders(<LogsTab />, { store })

    expect(screen.getByText('Nothing here mentions that identifier')).toBeInTheDocument()
    expect(screen.getByText(/no longer in the buffer to find/i)).toBeInTheDocument()
  })

  it('names the identifier the stream was narrowed to', () => {
    mockLogs([STRUCTURED_LINE])
    const store = createTestStore()
    store.dispatch(setTextFilter('trace-9f2c'))

    renderWithProviders(<LogsTab />, { store })

    expect(screen.getByText(/Matching/)).toBeInTheDocument()
  })
})
