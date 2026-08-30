/**
 * Shell tests for the metrics tab.
 *
 * `useMetrics` is mocked so these cover rendering and section switching
 * rather than polling; the hook's own network behaviour is exercised
 * through metricsService.test.js.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockUseMetrics } = vi.hoisted(() => ({ mockUseMetrics: vi.fn() }))

vi.mock('@/features/metrics/hooks/useMetrics', () => ({
  useMetrics: mockUseMetrics,
}))

import MetricsTab from './MetricsTab'

const OVERVIEW = {
  turns: 10,
  errored_turns: 1,
  error_rate: 0.1,
  mean_groundedness: 0.91,
  thumbs_up: 3,
  thumbs_down: 1,
  thumbs_up_rate: 0.75,
  qps: 2.5,
  turn_latency_seconds: { p50: { rag: 1.1 }, p95: { rag: 3.2 }, p99: { rag: 5.4 } },
  ttft_p95_seconds: { rag: 0.8 },
  cost: {
    by_model: [],
    tokens_in: 100,
    tokens_out: 50,
    estimated_cost_usd: 1.234,
    models_without_pricing: [],
  },
}

const LATENCY = {
  turns: 10,
  error_rate: 0.1,
  mean_latency_ms: 1200,
  mean_ttft_ms: 300,
  turn_latency_seconds: { p50: { rag: 1.1 }, p95: { rag: 3.2 }, p99: { rag: 5.4 } },
  ttft_seconds: { p50: { rag: 0.3 }, p95: { rag: 0.8 }, p99: { rag: 1.2 } },
  stage_p95_seconds: { retrieval: 0.4, generation: 2.1 },
  http_p95_seconds: { gateway: 0.05 },
  http_p99_seconds: { gateway: 0.09 },
  http_request_rate: { gateway: 1.5 },
  rpc_roundtrip_p95_seconds: { rag: 0.02 },
  series: {
    turn_latency_p95_series: [{ t: 1, v: 3.0 }, { t: 2, v: 3.4 }],
    ttft_p95_series: [{ t: 1, v: 0.7 }, { t: 2, v: 0.9 }],
    qps_series: [{ t: 1, v: 2.1 }, { t: 2, v: 2.5 }],
  },
}

const SECTION_DATA = { overview: OVERVIEW, latency: LATENCY, quality: null }

function mockSections({ promAvailable = true, generatedAt, tenantId = 'acme' } = {}) {
  mockUseMetrics.mockImplementation((section) => ({
    data: SECTION_DATA[section] ?? null,
    loading: false,
    error: null,
    promAvailable,
    lastUpdated: new Date('2026-08-25T12:00:00Z'),
    tenantId,
    prometheusScope: 'all_tenants',
    generatedAt: generatedAt === undefined ? new Date().toISOString() : generatedAt,
    refresh: vi.fn(),
  }))
}

describe('MetricsTab', () => {
  beforeEach(() => {
    mockUseMetrics.mockReset()
    mockSections()
  })

  it('renders the KPI row on the overview section', () => {
    render(<MetricsTab />)
    expect(screen.getByRole('heading', { name: 'Metrics' })).toBeInTheDocument()
    expect(screen.getByText('Turn latency p95')).toBeInTheDocument()
    expect(screen.getByText('Thumbs-up rate')).toBeInTheDocument()
    expect(screen.getByText('$1.23')).toBeInTheDocument()
    expect(screen.getByText('0.91')).toBeInTheDocument()
  })

  it('fetches only the section being viewed', () => {
    render(<MetricsTab />)
    // Every call is for the visible section — never all five endpoints.
    for (const call of mockUseMetrics.mock.calls) {
      expect(call[0]).toBe('overview')
    }
  })

  it('switches sections from the sub-nav', async () => {
    const user = userEvent.setup()
    render(<MetricsTab />)

    await user.click(screen.getByRole('button', { name: /Latency/i }))

    expect(screen.getByText('Recorded turns')).toBeInTheDocument()
    expect(screen.getByText("Where a turn's time goes")).toBeInTheDocument()
    expect(mockUseMetrics).toHaveBeenLastCalledWith('latency', expect.any(Object))
  })

  it('gives every button an accessible name', () => {
    render(<MetricsTab />)
    for (const button of screen.getAllByRole('button')) {
      const name = button.getAttribute('aria-label') || button.textContent.trim()
      expect(name, 'found a button with no accessible name').not.toBe('')
    }
  })

  describe('the trust contract above the panels', () => {
    it('names the tenant the response said it aggregated, and the denominator', () => {
      render(<MetricsTab />)

      expect(screen.getByText('Tenant · acme')).toBeInTheDocument()
      expect(screen.getByText(/last 24 hours · 10 turns/)).toBeInTheDocument()
    })

    it('says the tenant filter does not reach the Prometheus widgets', () => {
      render(<MetricsTab />)

      expect(screen.getByText('Global · all tenants')).toBeInTheDocument()
      expect(
        screen.getByText(/tenant filter does not apply to these/i)
      ).toBeInTheDocument()
    })

    it('drops the platform caveat on the section that has no Prometheus widgets', async () => {
      const user = userEvent.setup()
      render(<MetricsTab />)

      await user.click(screen.getByRole('button', { name: /Quality/i }))

      expect(screen.queryByText('Global · all tenants')).not.toBeInTheDocument()
    })

    it('says the data is delayed rather than showing an unqualified figure', () => {
      mockUseMetrics.mockReset()
      mockSections({ generatedAt: new Date(Date.now() - 4 * 60_000).toISOString() })
      render(<MetricsTab />)

      expect(screen.getByText('Data delayed 4m')).toBeInTheDocument()
    })

    it('reports freshness as unknown when the response carried no stamp', () => {
      mockUseMetrics.mockReset()
      mockSections({ generatedAt: null })
      render(<MetricsTab />)

      // Silence is reserved for data that is genuinely current. An unstamped
      // response says so instead of inheriting that silence.
      expect(screen.getByText('Freshness unknown')).toBeInTheDocument()
    })
  })

  describe('when the metrics store is unavailable', () => {
    beforeEach(() => {
      mockUseMetrics.mockReset()
      mockSections({ promAvailable: false })
    })

    it('degrades only the Prometheus widgets and keeps the Mongo-backed ones', async () => {
      const user = userEvent.setup()
      render(<MetricsTab />)
      await user.click(screen.getByRole('button', { name: /Latency/i }))

      // Prometheus-backed widgets say so...
      expect(screen.getAllByText(/Metrics store unavailable/i).length).toBeGreaterThan(0)

      // ...while the MongoDB-backed strip in the same panel still has values.
      expect(screen.getByText('Recorded turns')).toBeInTheDocument()
      expect(screen.getByText('Mean latency')).toBeInTheDocument()
      expect(screen.getByText('1.20 s')).toBeInTheDocument()
      expect(screen.getByText('300 ms')).toBeInTheDocument()
    })

    it('blanks Prometheus KPI cards without blanking the rest of the row', () => {
      render(<MetricsTab />)
      // Mongo-backed cards keep their values.
      expect(screen.getByText('$1.23')).toBeInTheDocument()
      expect(screen.getByText('10%')).toBeInTheDocument()
      // Prometheus-backed cards are present but empty.
      expect(screen.getByText('Turn latency p95')).toBeInTheDocument()
      expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    })
  })
})
