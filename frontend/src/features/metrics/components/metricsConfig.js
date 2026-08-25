/** Section definitions, labels, units, formatters and thresholds. */

import { Activity, Gauge, ShieldCheck } from 'lucide-react'

/** Shown wherever the API returned null — "not measured", not "zero". */
export const EMPTY = '—'

/**
 * Sub-nav sections. Retrieval and Pipeline arrive in phase 4 and are a
 * one-line addition here plus their panel component.
 */
export const METRICS_SECTIONS = [
  { id: 'overview', label: 'Overview', icon: Gauge },
  { id: 'latency', label: 'Latency', icon: Activity },
  { id: 'quality', label: 'Quality', icon: ShieldCheck },
]

export const WINDOW_OPTIONS = [
  { value: '1h', label: 'Last hour' },
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
]

export const DEFAULT_WINDOW = '24h'

// ---------------------------------------------------------------------------
// Formatters — one set, used by every panel and chart.
// ---------------------------------------------------------------------------

function isBlank(value) {
  return value === null || value === undefined || !Number.isFinite(Number(value))
}

/** Latency from seconds: milliseconds below 1000ms, seconds above. */
export function formatSeconds(seconds) {
  if (isBlank(seconds)) return EMPTY
  const ms = Number(seconds) * 1000
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`
}

/** Latency already expressed in milliseconds. */
export function formatMs(ms) {
  if (isBlank(ms)) return EMPTY
  return formatSeconds(Number(ms) / 1000)
}

/** Rates (QPS, requests/sec) to one decimal. */
export function formatRate(value) {
  if (isBlank(value)) return EMPTY
  return Number(value).toFixed(1)
}

/** A 0–1 fraction as an integer percentage. */
export function formatPercent(fraction) {
  if (isBlank(fraction)) return EMPTY
  return `${Math.round(Number(fraction) * 100)}%`
}

/** A 0–1 judge score, which is read as a score and not a percentage. */
export function formatScore(value) {
  if (isBlank(value)) return EMPTY
  return Number(value).toFixed(2)
}

export function formatCount(value) {
  if (isBlank(value)) return EMPTY
  return Number(value).toLocaleString()
}

export function formatCost(usd) {
  if (isBlank(usd)) return EMPTY
  return `$${Number(usd).toFixed(2)}`
}

export function formatTimestamp(date) {
  if (!date) return EMPTY
  const parsed = date instanceof Date ? date : new Date(date)
  return Number.isNaN(parsed.getTime()) ? EMPTY : parsed.toLocaleTimeString()
}

// ---------------------------------------------------------------------------
// Thresholds — a value past `warn` renders in the warning colour, past
// `danger` in the danger colour. Everything else stays default.
// ---------------------------------------------------------------------------

export const THRESHOLDS = {
  turn_latency_p95_seconds: { warn: 8, danger: 15 },
  ttft_p95_seconds: { warn: 2, danger: 5 },
  error_rate: { warn: 0.02, danger: 0.05 },
  hallucination_rate: { warn: 0.1, danger: 0.25 },
  guardrail_block_rate: { warn: 0.05, danger: 0.15 },
}

/** Variant for a metric where higher is worse. */
export function thresholdVariant(value, key) {
  const limits = THRESHOLDS[key]
  if (!limits || isBlank(value)) return 'default'
  const numeric = Number(value)
  if (numeric >= limits.danger) return 'danger'
  if (numeric >= limits.warn) return 'warning'
  return 'default'
}

/** Variant for a 0–1 score where higher is better. */
export function scoreVariant(value) {
  if (isBlank(value)) return 'default'
  const numeric = Number(value)
  if (numeric >= 0.8) return 'success'
  if (numeric >= 0.5) return 'warning'
  return 'danger'
}

// ---------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------

export const STAGE_LABELS = {
  retrieval: 'Retrieval',
  rerank: 'Rerank',
  generation: 'Generation',
  embedding: 'Embedding',
  memory: 'Memory',
  guardrail: 'Guardrail',
  judge: 'Judge',
}

export const SERVICE_LABELS = {
  gateway: 'Gateway',
  rag: 'RAG Orchestrator',
  files: 'File Service',
  llm_agent: 'LLM Agent',
  embedding: 'Embedding',
  reranker: 'Reranker',
  memory: 'Memory',
}

export const CONFIDENCE_LABELS = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

/** Fall back to the raw key rather than hiding an unmapped label. */
export function labelFor(map, key) {
  if (!key) return 'Unknown'
  return map[key] || String(key).replace(/_/g, ' ')
}

export const METRIC_LABELS = {
  turn_latency_p95: 'Turn latency p95',
  ttft_p95: 'TTFT p95',
  qps: 'Throughput',
  error_rate: 'Error rate',
  mean_groundedness: 'Mean groundedness',
  thumbs_up_rate: 'Thumbs-up rate',
  estimated_cost_usd: 'Estimated cost',
  // Deliberately not "Hallucination rate": this is a threshold over the
  // judge's groundedness score, not a claim-level measurement. Phase 6
  // replaces it with a real one.
  hallucination_rate_proxy_groundedness: 'Hallucination rate (proxy)',
  revision_rate: 'Revision rate',
  guardrail_block_rate: 'Guardrail block rate',
}

/** Message shown wherever a Prometheus-backed widget cannot be drawn. */
export const PROM_UNAVAILABLE = {
  title: 'Metrics store unavailable',
  description:
    'Prometheus is not reachable, so live time-series widgets are hidden. Stored per-turn metrics are unaffected.',
}
