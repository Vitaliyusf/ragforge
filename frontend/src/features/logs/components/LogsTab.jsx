'use client'

import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { motion } from 'framer-motion'
import {
  Activity,
  FileStack,
  Filter,
  Pause,
  Pin,
  Play,
  RefreshCw,
  Search,
  Server,
  Terminal,
  Trash2,
  X,
} from 'lucide-react'
import LoadingState from '@/components/feedback/LoadingState'
import DeepLink from '@/components/observability/DeepLink'
import { useLogs } from '@/features/logs'
import { parseLogEvent } from '@/lib/formatting/logs'
import { LOG_SEVERITIES, logsLinkForCorrelation } from '@/lib/observability/deepLinks'
import {
  setAutoRefresh,
  setLines,
  setPinnedToBottom,
  setSeverityFilter,
  setTextFilter,
  toggleService,
  toggleSeverity,
} from '@/store/slices/logsSlice'
import Badge from '@/components/ui/Badge'
import { serviceLabel } from '@/lib/terminology'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import Input from '@/components/ui/Input'
import PageHeader from '@/components/ui/PageHeader'
import { useI18n } from '@/i18n'
import { intlLocale } from '@/lib/formatting/datetime'
import { techLtrProps } from '@/lib/accessibility/direction'

const SEVERITY_COLORS = {
  error: 'var(--danger)',
  warning: 'var(--warning)',
  info: 'var(--info)',
  debug: 'var(--fg-soft)',
  trace: 'var(--primary)',
  unknown: 'var(--fg-soft)',
}

/** The severity vocabulary, owned by the observability module. */
const SEVERITY_OPTIONS = LOG_SEVERITIES

const SERVICE_COLORS = {
  gateway: '#4a9eff',
  files: '#10b981',
  embedding: '#8b5cf6',
  llm_agent: '#f59e0b',
  memory: '#ec4899',
  rag: '#06b6d4',
  reranker: '#14b8a6',
  vector_db: '#6366f1',
}

/** Enough of an id to recognise, short enough for a dense stream. */
function shortId(value) {
  const text = String(value)
  return text.length > 14 ? `${text.slice(0, 10)}…` : text
}

/**
 * One log entry, read as an event rather than as a line of text.
 *
 * Structured entries get their fields — time, origin, message — and their
 * correlation ids as controls that re-filter the stream around them. The raw
 * JSON stays available underneath, because the field the viewer does not know
 * how to show is exactly the one somebody eventually needs.
 *
 * A line that is not JSON renders as its own text. Nothing is invented for
 * it: an event with no structure is shown as having none.
 *
 * The row is pinned left-to-right in every locale. A log line is a technical
 * artifact — its severity, its origin path, its JSON and its message ordering
 * are all significant, and letting the bidi algorithm reflow them would
 * corrupt exactly the evidence an operator opened this screen to read. Only
 * the screen's chrome around it is translated.
 */
function LogEventRow({ event, severityColor, locale, eventDataLabel }) {
  const time = event.timestamp ? new Date(event.timestamp) : null
  const stamp = time && !Number.isNaN(time.getTime())
    ? time.toLocaleTimeString(intlLocale(locale))
    : null

  return (
    <div
      {...techLtrProps()}
      className="group flex items-start gap-2.5 rounded-lg border-l-2 px-2.5 py-2 text-left transition-colors [unicode-bidi:isolate]"
      style={{ borderLeftColor: severityColor }}
    >
      <span
        className="mt-0.5 w-12 shrink-0 text-xs font-semibold uppercase tracking-wide"
        style={{ color: severityColor }}
      >
        {event.severity}
      </span>
      <div className="min-w-0 flex-1">
        {stamp || event.location ? (
          <div className="flex flex-wrap items-center gap-x-2 text-xs text-text-muted">
            {stamp ? <span dir="ltr" className="tabular-nums">{stamp}</span> : null}
            {event.location ? <span className="truncate">{event.location}</span> : null}
          </div>
        ) : null}

        <p className="whitespace-pre-wrap break-words text-xs leading-relaxed text-text-secondary">
          {event.message}
        </p>

        {event.identifiers.length ? (
          <div className="mt-1 flex flex-wrap items-center gap-1">
            {event.identifiers.map((identifier) => (
              <DeepLink
                key={identifier.field}
                link={logsLinkForCorrelation({
                  id: identifier.value,
                  kindLabel: identifier.kindLabel,
                })}
              >
                <span className="font-mono">
                  {identifier.label} {shortId(identifier.value)}
                </span>
              </DeepLink>
            ))}
          </div>
        ) : null}

        {event.details ? (
          <details className="mt-1">
            <summary className="cursor-pointer text-xs text-text-muted">{eventDataLabel}</summary>
            <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-bg-tertiary p-2 text-xs text-text-muted">
              {JSON.stringify(event.details, null, 2)}
            </pre>
          </details>
        ) : null}
      </div>
    </div>
  )
}

function SummaryItem({ icon: Icon, label, value, color }) {
  return (
    <div className="flex items-center justify-between rounded-xl border border-border px-3 py-2.5">
      <span className="flex items-center gap-2 text-[13px] text-text-muted">
        <Icon size={13} style={{ color }} /> {label}
      </span>
      <span className="text-[15px] font-semibold tabular-nums" style={{ color }}>{value}</span>
    </div>
  )
}

export default function LogsTab() {
  const { locale, t } = useI18n()
  const dispatch = useDispatch()
  const selectedServices = useSelector((state) => state.logs.selectedServices)
  const lines = useSelector((state) => state.logs.lines)
  const autoRefresh = useSelector((state) => state.logs.autoRefresh)
  const textFilter = useSelector((state) => state.logs.textFilter)
  const severityFilter = useSelector((state) => state.logs.severityFilter)
  const pinnedToBottom = useSelector((state) => state.logs.pinnedToBottom)

  const {
    logs,
    loading,
    services,
    filteredLogs,
    fetchSelectedServicesLogs,
    fetchAllLogs,
    clearLogs,
  } = useLogs(selectedServices, lines, autoRefresh, textFilter, severityFilter)

  const logsEndRef = useRef(null)
  const logsContainerRef = useRef(null)
  const userScrolledUpRef = useRef(false)

  useEffect(() => {
    if (pinnedToBottom && !userScrolledUpRef.current && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [filteredLogs, pinnedToBottom])

  const handleScroll = useCallback(() => {
    if (!logsContainerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = logsContainerRef.current
    userScrolledUpRef.current = scrollHeight - scrollTop - clientHeight >= 100
  }, [])

  const getServiceColor = (service) => SERVICE_COLORS[service] || 'var(--fg-soft)'

  const groupedLogs = useMemo(() => filteredLogs.reduce((groups, log) => {
    if (!groups[log.service]) groups[log.service] = []
    groups[log.service].push(log)
    return groups
  }, {}), [filteredLogs])

  const totalLogsCount = Object.values(logs).reduce(
    (sum, serviceLogs) => sum + (serviceLogs?.logs?.length || 0),
    0
  )

  const filteredPercent = totalLogsCount > 0
    ? Math.round((filteredLogs.length / totalLogsCount) * 100)
    : 0

  const hasActiveFilters = Boolean(textFilter) || severityFilter.length < SEVERITY_OPTIONS.length

  return (
    <div className="mx-auto flex h-full min-h-0 w-full max-w-[1600px] flex-col overflow-y-auto p-3 md:p-6 xl:overflow-hidden">
      <PageHeader
        title={t('logs.liveLogs')}
        description={t('logs.description')}
        icon={Terminal}
        badge={
          autoRefresh
            ? <Badge variant="success" dot pulse>{t('logs.streaming')}</Badge>
            : <Badge variant="default" dot>{t('logs.paused')}</Badge>
        }
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={fetchAllLogs}
              disabled={loading}
              leftIcon={<Server size={13} />}
            >
              {t('logs.loadAll')}
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => fetchSelectedServicesLogs()}
              disabled={loading}
              loading={loading}
              leftIcon={<RefreshCw size={13} />}
            >
              {t('common.refresh')}
            </Button>
          </div>
        }
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:flex xl:min-h-0 xl:flex-col xl:overflow-y-auto xl:pe-1">
          <Card variant="elevated" padding="none" className="shrink-0">
            <div className="flex items-center justify-between border-b border-border px-4 py-3.5">
              <div>
                <h2 className="text-[15px] font-semibold text-text-primary">{t('logs.services')}</h2>
                <p className="mt-0.5 text-xs text-text-muted">{t('logs.chooseSources')}</p>
              </div>
              <Badge variant="default" size="xs">{selectedServices.length}/{services.length}</Badge>
            </div>
            <div className="grid grid-cols-2 gap-1.5 p-3 md:grid-cols-1">
              {services.map((service) => {
                const selected = selectedServices.includes(service)
                const serviceColor = getServiceColor(service)
                return (
                  <label
                    key={service}
                    className="flex cursor-pointer items-center gap-2.5 rounded-xl border px-2.5 py-2 text-[13px] transition-all"
                    style={{
                      background: selected ? `${serviceColor}12` : 'var(--surface-hover)',
                      borderColor: selected ? `${serviceColor}66` : 'var(--border)',
                      color: selected ? 'var(--fg)' : 'var(--fg-muted)',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => dispatch(toggleService(service))}
                      className="sr-only"
                    />
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: serviceColor, opacity: selected ? 1 : 0.45 }} />
                    {/* Service display names are canonical and stay English. */}
                    <span dir="ltr" className="min-w-0 flex-1 truncate text-start [unicode-bidi:isolate]">
                      {serviceLabel(service)}
                    </span>
                    {selected ? <span className="text-xs" style={{ color: serviceColor }}>✓</span> : null}
                  </label>
                )
              })}
            </div>
          </Card>

          <Card variant="elevated" padding="none" className="shrink-0">
            <div className="border-b border-border px-4 py-3.5">
              <h2 className="text-[15px] font-semibold text-text-primary">{t('logs.filterOutput')}</h2>
              <p className="mt-0.5 text-xs text-text-muted">{t('logs.narrowStream')}</p>
            </div>
            <div className="space-y-4 p-3">
              <div className="relative">
                <Input
                  value={textFilter}
                  onChange={(event) => dispatch(setTextFilter(event.target.value))}
                  placeholder={t('logs.searchText')}
                  aria-label={t('logs.searchText')}
                  // A log search accepts an English identifier typed into a
                  // Hebrew shell, so the field follows its own content.
                  dir="auto"
                  icon={Search}
                  size="sm"
                  className="pe-8"
                />
                {textFilter ? (
                  <button
                    type="button"
                    onClick={() => dispatch(setTextFilter(''))}
                    className="absolute end-2 top-1/2 flex h-6 w-6 -translate-y-1/2 items-center justify-center rounded-lg text-text-muted hover:bg-bg-tertiary hover:text-text-primary"
                    aria-label={t('logs.clearSearch')}
                  >
                    <X size={12} />
                  </button>
                ) : null}
              </div>

              <div>
                <div className="mb-2 flex items-center justify-between">
                  <span className="label-xs">{t('logs.severity')}</span>
                  <button
                    type="button"
                    onClick={() => dispatch(setSeverityFilter(SEVERITY_OPTIONS))}
                    className="text-xs font-medium text-primary hover:underline"
                  >
                    {t('logs.selectAll')}
                  </button>
                </div>
                <div className="grid grid-cols-3 gap-1.5">
                  {SEVERITY_OPTIONS.map((severity) => {
                    const selected = severityFilter.includes(severity)
                    const color = SEVERITY_COLORS[severity]
                    return (
                      <button
                        key={severity}
                        type="button"
                        onClick={() => dispatch(toggleSeverity(severity))}
                        className="rounded-lg border px-2 py-1.5 text-xs font-medium capitalize transition-colors"
                        style={{
                          background: selected ? `${color}14` : 'transparent',
                          borderColor: selected ? `${color}66` : 'var(--border)',
                          color: selected ? color : 'var(--fg-soft)',
                        }}
                      >
                        {severity}
                      </button>
                    )
                  })}
                </div>
              </div>

              <Input
                label={t('logs.linesToKeep')}
                type="number"
                dir="ltr"
                value={String(lines)}
                onChange={(event) => dispatch(setLines(parseInt(event.target.value) || 100))}
                min={10}
                max={1000}
                size="sm"
              />

              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => dispatch(setAutoRefresh(!autoRefresh))}
                  className="flex items-center justify-center gap-1.5 rounded-xl border px-2 py-2 text-xs font-medium transition-colors"
                  style={{
                    background: autoRefresh ? 'var(--success-soft)' : 'var(--surface-hover)',
                    borderColor: autoRefresh ? 'rgba(34,197,94,0.3)' : 'var(--border)',
                    color: autoRefresh ? 'var(--success)' : 'var(--fg-muted)',
                  }}
                >
                  {autoRefresh ? <Pause size={12} /> : <Play size={12} />}
                  {t(autoRefresh ? 'logs.streaming' : 'logs.paused')}
                </button>
                <button
                  type="button"
                  onClick={() => dispatch(setPinnedToBottom(!pinnedToBottom))}
                  className="flex items-center justify-center gap-1.5 rounded-xl border px-2 py-2 text-xs font-medium transition-colors"
                  style={{
                    background: pinnedToBottom ? 'var(--primary-soft)' : 'var(--surface-hover)',
                    borderColor: pinnedToBottom ? 'var(--border-focus)' : 'var(--border)',
                    color: pinnedToBottom ? 'var(--primary)' : 'var(--fg-muted)',
                  }}
                >
                  <Pin size={12} /> {t(pinnedToBottom ? 'logs.pinned' : 'logs.freeScroll')}
                </button>
              </div>
            </div>
          </Card>

          <Card variant="elevated" padding="sm" className="shrink-0 md:col-span-2 xl:col-span-1">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h2 className="text-[13px] font-semibold text-text-primary">{t('logs.currentView')}</h2>
                <p className="mt-0.5 text-xs text-text-muted">
                  {t('logs.percentOfLoaded', { percent: filteredPercent })}
                </p>
              </div>
              <Button variant="danger-ghost" size="icon-sm" onClick={clearLogs} aria-label={t('logs.clearLogs')}>
                <Trash2 size={13} />
              </Button>
            </div>
            <div className="space-y-2">
              <SummaryItem icon={FileStack} label={t('logs.loaded')} value={totalLogsCount} color="var(--primary)" />
              <SummaryItem icon={Filter} label={t('logs.visible')} value={filteredLogs.length} color="var(--success)" />
              <SummaryItem icon={Server} label={t('logs.sources')} value={selectedServices.length} color="var(--warning)" />
            </div>
          </Card>
        </aside>

        <section className="flex min-h-[580px] min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-bg-elevated shadow-md xl:min-h-0">
          <div className="flex flex-col gap-3 border-b border-border px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-success" />
                <h2 className="truncate text-[15px] font-semibold text-text-primary">
                  {selectedServices.length === 1
                    ? t('logs.serviceOutputFor', { service: serviceLabel(selectedServices[0]) })
                    : t('logs.serviceStreams', { count: selectedServices.length })}
                </h2>
              </div>
              <p className="mt-0.5 text-xs text-text-muted">
                {t('logs.visibleEvents', { count: filteredLogs.length })}
              </p>
            </div>
            <div className="flex items-center gap-1.5">
              {/* Arriving from a deep link means arriving already filtered.
                  Naming the term is what stops an empty stream reading as a
                  quiet system. */}
              {textFilter ? (
                <Badge variant="primary" size="xs" icon={Filter} title={textFilter}>
                  {t('logs.matching', {
                    term: textFilter.length > 18 ? `${textFilter.slice(0, 16)}…` : textFilter,
                  })}
                </Badge>
              ) : hasActiveFilters ? (
                <Badge variant="primary" size="xs" icon={Filter}>{t('logs.filtered')}</Badge>
              ) : null}
              {/* The auto-refresh toggle beside this already says whether the
                  stream is following; a second "Live" chip here was one of
                  four things in the app claiming liveness in its own words. */}
              {pinnedToBottom ? <Badge variant="accent" size="xs" icon={Pin}>{t('logs.pinned')}</Badge> : null}
            </div>
          </div>

          <div
            ref={logsContainerRef}
            onScroll={handleScroll}
            className="min-h-0 flex-1 overflow-y-auto bg-[var(--bg)] p-3 font-mono scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent md:p-4"
          >
            {loading && filteredLogs.length === 0 ? (
              <LoadingState label={t('logs.loadingOutput')} minHeight={360} />
            ) : filteredLogs.length === 0 ? (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex min-h-[360px] flex-col items-center justify-center rounded-2xl border border-dashed border-border px-6 text-center"
              >
                <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-soft text-primary">
                  <Terminal size={23} />
                </span>
                <h3 className="mt-4 text-[15px] font-semibold text-text-primary">
                  {textFilter
                    ? t('logs.noIdentifierMatch')
                    : hasActiveFilters
                      ? t('logs.noMatches')
                      : t('logs.empty')}
                </h3>
                <p className="mt-1 max-w-sm text-[13px] leading-relaxed text-text-muted">
                  {textFilter
                    ? t('logs.noIdentifierMatchDescription', { lines })
                    : hasActiveFilters
                      ? t('logs.widenFilters')
                      : t('logs.chooseAndRefresh')}
                </p>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => fetchSelectedServicesLogs()}
                  disabled={loading}
                  loading={loading}
                  className="mt-4"
                  leftIcon={<RefreshCw size={13} />}
                >
                  {t('logs.refresh')}
                </Button>
              </motion.div>
            ) : (
              <div className="space-y-4">
                {Object.entries(groupedLogs).map(([service, serviceLogs], groupIndex) => (
                  <motion.div
                    key={service}
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: Math.min(groupIndex, 6) * 0.025 }}
                  >
                    <div className="sticky top-0 z-10 mb-1.5 flex items-center gap-2 rounded-xl border border-border px-3 py-2 backdrop-blur">
                      <span className="h-2 w-2 rounded-full" style={{ background: getServiceColor(service) }} />
                      <span dir="ltr" className="text-xs font-semibold text-text-primary [unicode-bidi:isolate]">
                        {serviceLabel(service)}
                      </span>
                      <span className="ms-auto text-xs text-text-muted">
                        {t('logs.eventCount', { count: serviceLogs.length })}
                      </span>
                    </div>

                    <div className="space-y-0.5">
                      {serviceLogs.map((log, index) => {
                        const event = parseLogEvent(log.line)
                        const severity = log.severity || event.severity || 'unknown'
                        const severityColor = SEVERITY_COLORS[severity] || SEVERITY_COLORS.unknown
                        return (
                          <LogEventRow
                            key={`${log.service}-${log.index}-${index}`}
                            event={{ ...event, severity }}
                            severityColor={severityColor}
                            locale={locale}
                            eventDataLabel={t('logs.eventData')}
                          />
                        )
                      })}
                    </div>
                  </motion.div>
                ))}
                <div ref={logsEndRef} />
              </div>
            )}
          </div>

          <div className="flex items-center gap-4 border-t border-border px-4 py-2 text-xs text-text-muted">
            <span className="flex items-center gap-1.5">
              <Activity size={11} className="text-success" />{' '}
              {t(autoRefresh ? 'logs.streamActive' : 'logs.streamPaused')}
            </span>
            <span>{t('logs.eventsOfTotal', { visible: filteredLogs.length, total: totalLogsCount })}</span>
            <span className="ms-auto hidden sm:inline">{t('logs.latestLines', { lines })}</span>
          </div>
        </section>
      </div>
    </div>
  )
}
