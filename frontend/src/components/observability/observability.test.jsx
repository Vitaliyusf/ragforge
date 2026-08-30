/**
 * OBS-UX-01 — the trust contract and the jump, on screen.
 *
 * Two rules are visual, so they are tested visually: a global figure has to
 * say so where it is read, and a link that cannot be built must not appear as
 * a button that goes nowhere.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { NavigationProvider } from '@/components/layout/NavigationContext'
import DeepLink from './DeepLink'
import { FreshnessBadge, MetricTrustLine, ScopeBadge } from './MetricMeta'
import { logsLinkForService } from '@/lib/observability/deepLinks'
import {
  METRIC_SOURCE,
  describeFreshness,
  describeMetric,
  describeScope,
} from '@/lib/observability/metricMeta'

describe('scope and freshness badges', () => {
  it('says a Prometheus figure is global, where the figure is read', () => {
    render(<ScopeBadge scope={describeScope({ source: METRIC_SOURCE.PROMETHEUS })} />)

    const badge = screen.getByText('Global · all tenants')
    expect(badge).toHaveAttribute('title', expect.stringMatching(/no tenant label/i))
  })

  it('stays silent while the data is current, so the warning slot stays meaningful', () => {
    const { container } = render(
      <FreshnessBadge
        freshness={describeFreshness('2026-01-01T12:00:00Z', {
          now: Date.parse('2026-01-01T12:00:05Z'),
        })}
      />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('names the delay once the data has stopped keeping up', () => {
    render(
      <FreshnessBadge
        freshness={describeFreshness('2026-01-01T11:56:00Z', {
          now: Date.parse('2026-01-01T12:00:00Z'),
        })}
      />
    )
    expect(screen.getByText('Data delayed 4m')).toBeInTheDocument()
  })

  it('puts scope, range and denominator on one line', () => {
    render(
      <MetricTrustLine
        meta={describeMetric({
          source: METRIC_SOURCE.METRICS_STORE,
          tenantId: 'acme',
          window: '24h',
          sampleCount: 0,
          sampleNoun: 'turn',
          generatedAt: '2026-01-01T12:00:00Z',
          now: Date.parse('2026-01-01T12:00:02Z'),
        })}
      />
    )

    expect(screen.getByText('Tenant · acme')).toBeInTheDocument()
    // "No turns in this range" rather than an em dash: which kind of nothing
    // this is, is the whole point.
    expect(screen.getByText(/last 24 hours · No turns in this range/)).toBeInTheDocument()
  })
})

describe('DeepLink', () => {
  it('renders nothing when the builder refused to build a link', () => {
    const { container } = render(<DeepLink link={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('hands the link to the shell rather than navigating on its own', async () => {
    const user = userEvent.setup()
    const followDeepLink = vi.fn()
    const link = logsLinkForService('rag')

    render(
      <NavigationProvider value={{ navigate: vi.fn(), followDeepLink }}>
        <DeepLink link={link} />
      </NavigationProvider>
    )

    await user.click(screen.getByRole('button', { name: /View Logs/i }))
    expect(followDeepLink).toHaveBeenCalledWith(link)
  })

  it('renders outside the shell without throwing, so a panel stays testable', () => {
    render(<DeepLink link={logsLinkForService('rag')} />)
    expect(screen.getByRole('button', { name: /View Logs/i })).toBeInTheDocument()
  })
})
