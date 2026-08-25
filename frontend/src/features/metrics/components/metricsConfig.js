/** Section definitions, labels, units, formatters and thresholds. */

import { Activity, FlaskConical, Gauge, Search, ShieldCheck, Workflow } from 'lucide-react'

/** Shown wherever the API returned null — "not measured", not "zero". */
export const EMPTY = '—'

/**
 * Sub-nav sections. One entry per panel, in display order.
 *
 * `standalone` marks a section that owns its own data loading instead of
 * going through `useMetrics`. Eval is not a windowed aggregation — a run is
 * a document with its own lifecycle — so the window and tenant selectors do
 * not apply to it.
 */
export const METRICS_SECTIONS = [
  { id: 'overview', label: 'Overview', icon: Gauge },
  { id: 'latency', label: 'Latency', icon: Activity },
  { id: 'retrieval', label: 'Retrieval', icon: Search },
  { id: 'quality', label: 'Quality', icon: ShieldCheck },
  { id: 'pipeline', label: 'Pipeline', icon: Workflow },
  { id: 'eval', label: 'Eval', icon: FlaskConical, standalone: true },
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

/** A count that is meaningfully fractional, such as a mean per query. */
export function formatDecimal(value) {
  if (isBlank(value)) return EMPTY
  return Number(value).toFixed(1)
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
  empty_retrieval_rate: { warn: 0.1, danger: 0.25 },
  retrieval_filtered_rate: { warn: 0.2, danger: 0.4 },
  // Messages, not a rate. A few hundred behind is a blip; five figures is a
  // consumer that is not keeping up.
  kafka_consumer_lag: { warn: 1000, danger: 10000 },
  stuck_files: { warn: 1, danger: 5 },
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

export const FUNNEL_STEP_LABELS = {
  uploaded: 'Uploaded',
  extracted: 'Extracted',
  chunked: 'Chunked',
  embedded: 'Embedded',
  indexed: 'Indexed',
}

export const FILTER_REASON_LABELS = {
  retrieval_not_allowed: 'Retrieval not allowed',
  review_removed: 'Removed in review',
}

export const CONFIDENCE_LABELS = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

/** The judge's claim-level hallucination verdicts. */
export const HALLUCINATION_VERDICT_LABELS = {
  none: 'None',
  minor: 'Minor',
  severe: 'Severe',
}

export const HALLUCINATION_VERDICT_VARIANTS = {
  none: 'success',
  minor: 'warning',
  severe: 'danger',
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
  // Two different measures, never merged into one number. The first is the
  // claim-level judgement; the second is the older threshold over a single
  // groundedness score, kept for turns recorded before the judge returned
  // verdicts. Their labels say which is which because their denominators
  // are different populations.
  hallucination_rate: 'Hallucination rate',
  hallucination_severe_rate: 'Severe hallucinations',
  hallucination_rate_proxy_groundedness: 'Hallucination rate (proxy)',
  mean_unsupported_claims: 'Unsupported claims per answer',
  mean_citation_precision: 'Citation precision',
  mean_citation_recall: 'Citation recall',
  citation_f1: 'Citation F1',
  mean_citation_count: 'Citations per answer',
  mean_cited_chunk_ratio: 'Chunks cited',
  revision_rate: 'Revision rate',
  guardrail_block_rate: 'Guardrail block rate',
  hit_rate: 'Retrieval hit rate',
  empty_retrieval_rate: 'Empty retrievals',
  mean_chunk_count: 'Chunks per query',
  vector_search_p95: 'Vector search p95',
  mean_score_gap: 'Mean score gap',
  reranker_changed_top1_rate: 'Reranker lift',
  reranker_p95_seconds: 'Reranker p95',
  retrieval_filtered_rate: 'Filtered out',
  embedding_chunk_rate: 'Embedding throughput',
  kafka_consumer_lag: 'Consumer lag',
  stuck_files: 'Stuck in processing',
  vectors: 'Vectors indexed',
  recall_at_5: 'Recall@5',
}

/**
 * Shown when a window contains turns from both before and after the phase-6
 * deploy. The two hallucination measures count different populations, so the
 * panel shows both and says so rather than averaging them into one figure
 * that describes neither.
 */
export const MIXED_HALLUCINATION_NOTE =
  'Some turns in this window predate claim-level judging and carry no ' +
  'verdict. The two rates below count different turns and must not be ' +
  'compared or combined.'

/** Shown beside citation precision, whose denominator excludes some answers. */
export const CITATION_DENOMINATOR_NOTE =
  'An answer that cited nothing has no precision to measure and is excluded ' +
  'rather than scored zero, so this mean can cover far fewer answers than ' +
  'the window holds.'

/** Shown beside any figure Prometheus supplies: these carry no tenant label. */
export const PLATFORM_SCOPE_NOTE =
  'Platform-wide across all tenants — this figure carries no tenant label.'

/** Every cost on the tab is an estimate from a static price table. */
export const COST_ESTIMATE_NOTE =
  'Estimated from the configured per-token price table, not billed amounts.'

/** Message shown wherever a Prometheus-backed widget cannot be drawn. */
export const PROM_UNAVAILABLE = {
  title: 'Metrics store unavailable',
  description:
    'Prometheus is not reachable, so live time-series widgets are hidden. Stored per-turn metrics are unaffected.',
}

// ---------------------------------------------------------------------------
// Eval harness
// ---------------------------------------------------------------------------

/** The k values every run reports. Fixed by the stored `results` shape. */
export const EVAL_K_VALUES = [1, 3, 5, 10, 20]

/** The k the run-history chart tracks — deep enough to be stable, shallow
 *  enough that a real ranking change still moves it. */
export const EVAL_HISTORY_K = '5'

export const RUN_STATUS_LABELS = {
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
}

export const RUN_STATUS_VARIANTS = {
  running: 'info',
  completed: 'success',
  failed: 'danger',
}

export const EVAL_METRIC_LABELS = {
  mrr: 'MRR',
  ndcg_at_10: 'nDCG@10',
  recall_at_k: 'Recall@k',
  precision_at_k: 'Precision@k',
  hit_rate_at_k: 'Hit rate@k',
  items_evaluated: 'Items scored',
  items_skipped: 'Items skipped',
  items_failed: 'Items failed',
  mean_latency_ms: 'Mean retrieval latency',
}

export const CONFIG_SNAPSHOT_LABELS = {
  top_k_documents: 'Top-k documents',
  reranker_enabled: 'Reranker',
  reranker_top_k: 'Reranker top-k',
  hybrid_search_enabled: 'Hybrid search',
  hybrid_search_alpha: 'Hybrid alpha',
  min_similarity_threshold: 'Min similarity',
  mode: 'Run mode',
  embedding_model: 'Embedding model',
  vector_collection: 'Vector collection',
  chunk_strategy: 'Chunk strategy',
}

export const EVAL_MODE_LABELS = {
  retrieval: 'Retrieval only',
  end_to_end: 'End-to-end',
}

/** Said plainly before an end-to-end run, which is the one that spends money. */
export const EVAL_MODE_HELP = {
  retrieval:
    'Runs retrieval only. No model is called, so the run is free and finishes in seconds.',
  end_to_end:
    'Generates and judges an answer for every item. This calls the model twice per item and takes minutes, not seconds.',
}

/** Shown when the estimate covers a model with no configured price. */
export const UNPRICED_MODEL_NOTE =
  'This model has no configured price, so the estimate is $0.00 because ' +
  'nothing here is priced — not because the run is free.'

export const EVAL_ANSWER_METRIC_LABELS = {
  groundedness: 'Mean groundedness',
  hallucination_rate: 'Hallucination rate',
  hallucination_severe_rate: 'Severe hallucinations',
  citation_precision: 'Citation precision',
  citation_recall: 'Citation recall',
  unsupported_claims: 'Unsupported claims per answer',
  items_judged: 'Items judged',
}

export const MATCH_MODE_LABELS = {
  chunk_id: 'Chunk-level',
  file_id: 'File-level',
  mixed: 'Mixed',
}

/** Shown whenever the two most recent runs ran under different settings. */
export const CONFIG_DIFF_NOTE =
  'These runs used different retrieval settings, so the difference between ' +
  'their scores is not a measure of retrieval quality alone.'

/** Shown for snapshot fields the rag service cannot observe. */
export const UNOBSERVED_NOTE =
  'Not captured — the rag service cannot see this setting, so two runs ' +
  'cannot be compared on it.'

/** Shown beside file-level runs, which score more generously than chunk-level. */
export const FILE_MATCH_NOTE =
  'Scored at file level: any chunk from a relevant file counts as a hit, ' +
  'which reads higher than chunk-level matching on the same retrieval.'

/** The empty state's explainer. A golden set is hand-built, and saying so is
 *  more useful than a button that implies otherwise. */
export const GOLDEN_SET_HELP = [
  'Pick 20–50 real questions your users actually ask.',
  'For each one, open the documents and record the chunk ids that genuinely answer it.',
  'Upload them as JSON. Re-run after any retrieval change to see the effect.',
]

/** Render a boolean setting as a word rather than "true"/"false". */
export function formatSetting(value) {
  if (value === null || value === undefined || value === '') return EMPTY
  if (typeof value === 'boolean') return value ? 'On' : 'Off'
  return String(value)
}
