'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle, BarChart3, RefreshCw } from 'lucide-react'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import PageHeader from '@/components/ui/PageHeader'
import Select, { SelectItem } from '@/components/ui/Select'
import TabSkeleton from '@/components/ui/TabSkeleton'
import { cn } from '@/lib/utils'
import { useMetrics } from '../hooks/useMetrics'
import KpiHeader from './KpiHeader'
import LatencyPanel from './LatencyPanel'
import PipelinePanel from './PipelinePanel'
import QualityPanel from './QualityPanel'
import RetrievalPanel from './RetrievalPanel'
import {
  DEFAULT_WINDOW,
  METRICS_SECTIONS,
  WINDOW_OPTIONS,
  formatTimestamp,
} from './metricsConfig'

/** Sentinel for "whichever tenant the caller belongs to". */
const OWN_TENANT = '__own__'

/**
 * Sections this tab used to own.
 *
 * Eval is a top-level workspace now. Arriving here asking for it is not an
 * error and must not render an empty tab: the request is handed to the
 * shell, which switches to the Eval destination, and Metrics falls back to
 * its own first section in the meantime.
 */
const RELOCATED_SECTIONS = { eval: 'eval' }

export default function MetricsTab({ section: requestedSection, onNavigate }) {
  const relocatedTo = RELOCATED_SECTIONS[requestedSection]
  const known = METRICS_SECTIONS.some((entry) => entry.id === requestedSection)
  const [section, setSection] = useState(known ? requestedSection : METRICS_SECTIONS[0].id)
  const [windowRange, setWindowRange] = useState(DEFAULT_WINDOW)
  const [tenant, setTenant] = useState(OWN_TENANT)

  useEffect(() => {
    if (relocatedTo) onNavigate?.(relocatedTo)
  }, [relocatedTo, onNavigate])

  // One section, one request. Changing the sub-nav swaps the endpoint rather
  // than loading all five.
  const { data, loading, error, promAvailable, lastUpdated, refresh } = useMetrics(section, {
    window: windowRange,
    tenantId: tenant === OWN_TENANT ? '' : tenant,
  })

  const panelProps = { data, loading, error, promAvailable, onRetry: refresh }

  return (
    <div className="mx-auto flex h-full w-full max-w-7xl flex-col gap-5 overflow-y-auto px-3 py-4 md:px-6 md:py-5">
      <PageHeader
        title="Metrics"
        description={
          lastUpdated
            ? `Last updated ${formatTimestamp(lastUpdated)}`
            : 'Latency, throughput and answer quality for this workspace'
        }
        icon={BarChart3}
        badge={
          !promAvailable && (
            <Badge variant="warning" dot>
              Metrics store unavailable
            </Badge>
          )
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={windowRange}
              onValueChange={setWindowRange}
              className="w-[168px]"
              aria-label="Time window"
            >
              {WINDOW_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </Select>

            {/* No endpoint enumerates tenants, so this offers the caller's own
                tenant and whichever one the response actually reported. */}
            <Select
              value={tenant}
              onValueChange={setTenant}
              className="w-[168px]"
              aria-label="Tenant"
            >
              <SelectItem value={OWN_TENANT}>Current tenant</SelectItem>
            </Select>

            <Button
              variant="secondary"
              size="sm"
              onClick={refresh}
              disabled={loading}
              leftIcon={<RefreshCw size={13} className={loading ? 'animate-spin' : ''} />}
            >
              Refresh
            </Button>
          </div>
        }
      />

      {/* Sub-nav, driven entirely by METRICS_SECTIONS. */}
      <nav aria-label="Metrics sections">
        <ul className="flex flex-wrap gap-1.5">
          {METRICS_SECTIONS.map(({ id, label, icon: Icon }) => {
            const active = id === section
            return (
              <li key={id}>
                <button
                  type="button"
                  onClick={() => setSection(id)}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[14px] font-medium',
                    'transition-colors duration-150',
                    'focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)]'
                  )}
                  style={{
                    background: active ? 'var(--surface-hover)' : 'transparent',
                    color: active ? 'var(--fg)' : 'var(--fg-muted)',
                  }}
                >
                  <Icon size={14} />
                  {label}
                </button>
              </li>
            )
          })}
        </ul>
      </nav>

      {section === 'overview' && <OverviewSection {...panelProps} />}
      {section === 'latency' && <LatencyPanel {...panelProps} />}
      {section === 'retrieval' && <RetrievalPanel {...panelProps} />}
      {section === 'quality' && <QualityPanel {...panelProps} />}
      {section === 'pipeline' && <PipelinePanel {...panelProps} />}
    </div>
  )
}

/**
 * Overview owns its own states like every other panel, so a failing
 * overview request cannot blank the rest of the tab.
 */
function OverviewSection({ data, loading, error, promAvailable, onRetry }) {
  if (loading && !data) return <TabSkeleton />

  if (error) {
    return (
      <div
        className="flex items-center justify-between gap-3 rounded-xl px-4 py-3 text-[15px]"
        style={{
          background: 'var(--danger-soft)',
          border: '1px solid rgba(239,68,68,0.25)',
          color: 'var(--danger)',
        }}
      >
        <span className="flex items-center gap-2.5">
          <AlertTriangle size={15} />
          {error}
        </span>
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      </div>
    )
  }

  return <KpiHeader data={data} promAvailable={promAvailable} />
}
