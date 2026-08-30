/**
 * OBS-UX-01 — what the health board is allowed to claim.
 *
 * The board reports probes. It must say which probes, must not let a green
 * board be read as an SLO statement, and must survive having no services to
 * show — the empty branch previously referenced an icon the module never
 * imported and threw on the way to rendering it.
 */
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockUseHealth } = vi.hoisted(() => ({ mockUseHealth: vi.fn() }))

vi.mock('../hooks/useHealth', () => ({ useHealth: mockUseHealth }))

import HealthDashboard from './HealthDashboard'

function mockHealth(health, { loading = false, error = null } = {}) {
  mockUseHealth.mockReturnValue({ health, loading, error, history: [], refresh: vi.fn() })
}

const NOW_SECONDS = Date.parse('2026-01-01T12:00:00Z') / 1000

describe('HealthDashboard', () => {
  beforeEach(() => {
    mockUseHealth.mockReset()
    vi.useRealTimers()
  })

  it('renders the empty board instead of throwing when no service reported', () => {
    mockHealth({ status: 'unknown', timestamp: NOW_SECONDS, services: {} })

    render(<HealthDashboard />)

    expect(screen.getByText('No service data')).toBeInTheDocument()
  })

  it('refuses to let a green board be read as a service objective', () => {
    mockHealth({
      status: 'healthy',
      timestamp: NOW_SECONDS,
      services: { rag: { name: 'rag', status: 'healthy', live: true, ready: true } },
    })

    render(<HealthDashboard />)

    expect(screen.getByText(/No error budget or latency objective is evaluated/i)).toBeInTheDocument()
  })

  it("says the probes are platform-wide rather than this tenant's", () => {
    mockHealth({ status: 'healthy', timestamp: NOW_SECONDS, services: {} })

    render(<HealthDashboard />)

    expect(screen.getByText('Global · all tenants')).toBeInTheDocument()
  })

  it('says the board is stale rather than showing old probes as current', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T12:05:00Z'))
    mockHealth({ status: 'healthy', timestamp: NOW_SECONDS, services: {} })

    render(<HealthDashboard />)

    expect(screen.getByText(/Data stale/)).toBeInTheDocument()
    vi.useRealTimers()
  })
})
