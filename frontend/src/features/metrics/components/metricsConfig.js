/** Section definitions, labels, units, formatters and thresholds. */

import { Activity, Gauge, Search, ShieldCheck, Workflow } from 'lucide-react'
import { SERVICE_LABELS } from '@/lib/terminology'
import { intlLocale } from '@/lib/formatting/datetime'
import { DEFAULT_LOCALE } from '@/i18n/locale'
import { translate } from '@/i18n/translate'

/** Shown wherever the API returned null — "not measured", not "zero". */
export const EMPTY = '—'

/**
 * Sub-nav sections. One entry per panel, in display order.
 *
 * Every section here is a windowed aggregation over live traffic. Eval is
 * not — a run is a document with its own lifecycle, and the window and
 * tenant selectors mean nothing to it — so it is a top-level workspace of
 * its own rather than a sixth entry in this list.
 */
export const METRICS_SECTIONS = [
  { id: 'overview', labelKey: 'metrics.section.overview', icon: Gauge },
  { id: 'latency', labelKey: 'metrics.section.latency', icon: Activity },
  { id: 'retrieval', labelKey: 'metrics.section.retrieval', icon: Search },
  { id: 'quality', labelKey: 'metrics.section.quality', icon: ShieldCheck },
  { id: 'pipeline', labelKey: 'metrics.section.pipeline', icon: Workflow },
]

/**
 * Where each section's headline sample count lives, and what it counts.
 *
 * Every panel is an aggregation, and an aggregation without its denominator
 * is a rumour. This is the denominator the section header states.
 */
export const SECTION_SAMPLES = {
  overview: { get: (data) => data?.turns, noun: 'turn' },
  latency: { get: (data) => data?.turns, noun: 'turn' },
  retrieval: { get: (data) => data?.turns, noun: 'turn' },
  quality: { get: (data) => data?.turns, noun: 'turn' },
  pipeline: { get: (data) => data?.ingestion?.funnel?.files, noun: 'file' },
}

/**
 * Sections that render at least one Prometheus-backed widget.
 *
 * Quality is the exception: it is entirely MongoDB-backed, so the
 * platform-scope caveat would be a warning about nothing on that page.
 */
export const PROMETHEUS_SECTIONS = new Set(['overview', 'latency', 'retrieval', 'pipeline'])

export const WINDOW_OPTIONS = [
  { value: '1h', labelKey: 'metrics.window.1h' },
  { value: '24h', labelKey: 'metrics.window.24h' },
  { value: '7d', labelKey: 'metrics.window.7d' },
  { value: '30d', labelKey: 'metrics.window.30d' },
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

export function formatTimestamp(date, locale) {
  if (!date) return EMPTY
  const parsed = date instanceof Date ? date : new Date(date)
  return Number.isNaN(parsed.getTime()) ? EMPTY : parsed.toLocaleTimeString(intlLocale(locale))
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
//
// Two kinds live below, and only one of them is copy.
//
//   * Chrome — section names, window ranges, verdict and confidence words —
//     carries a `labelKey` and is translated.
//   * Metric and stage *names* — METRIC_LABELS, STAGE_LABELS,
//     FUNNEL_STEP_LABELS, EVAL_METRIC_LABELS, CONFIG_SNAPSHOT_LABELS — stay
//     canonical English. They name Prometheus series, pipeline stages and
//     stored config keys that an operator correlates against dashboards,
//     alert rules and the backend's own field names; translating "TTFT p95"
//     or "nDCG@10" would break that correspondence and help nobody.
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

/** Re-exported from the shared terminology so metrics cannot drift from health. */
export { SERVICE_LABELS }

export const FUNNEL_STEP_LABELS = {
  uploaded: 'Uploaded',
  extracted: 'Extracted',
  chunked: 'Chunked',
  embedded: 'Embedded',
  indexed: 'Indexed',
}

export const FILTER_REASON_LABEL_KEYS = {
  retrieval_not_allowed: 'metrics.filterReason.notAllowed',
  review_removed: 'metrics.filterReason.reviewRemoved',
}

export const CONFIDENCE_LABEL_KEYS = {
  high: 'metrics.confidence.high',
  medium: 'metrics.confidence.medium',
  low: 'metrics.confidence.low',
}

/** The judge's claim-level hallucination verdicts. */
export const HALLUCINATION_VERDICT_LABEL_KEYS = {
  none: 'metrics.verdict.none',
  minor: 'metrics.verdict.minor',
  severe: 'metrics.verdict.severe',
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

/**
 * The same fallback, for the tables that hold translation keys.
 *
 * A key the backend added but this build has no wording for reads as its
 * own raw name rather than as a guessed translation.
 */
export function translatedLabelFor(keyMap, key, t) {
  if (!key) return t('common.unknown')
  const messageKey = keyMap[key]
  return messageKey ? t(messageKey) : String(key).replace(/_/g, ' ')
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
 * Shown beside any figure Prometheus supplies: these carry no tenant label.
 * Owned by the shared trust contract so Health and Metrics cannot describe
 * the same scope two ways.
 */
export { PLATFORM_SCOPE_NOTE } from '@/lib/observability/metricMeta'

/** Message shown wherever a Prometheus-backed widget cannot be drawn. */
export const PROM_UNAVAILABLE = {
  titleKey: 'metrics.storeUnavailable',
  descriptionKey: 'metrics.storeUnavailableDescription',
}

// ---------------------------------------------------------------------------
// Eval harness
//
// Rendered by the top-level Eval workspace (`src/features/eval`), not by any
// panel in this tab. The labels live here because the eval run document and
// the metrics panels share the same formatters and metric vocabulary.
// ---------------------------------------------------------------------------

/** The k values every run reports. Fixed by the stored `results` shape. */
export const EVAL_K_VALUES = [1, 3, 5, 10, 20]

/** The k the run-history chart tracks — deep enough to be stable, shallow
 *  enough that a real ranking change still moves it. */
export const EVAL_HISTORY_K = '5'

export const RUN_STATUS_LABEL_KEYS = {
  running: 'eval.runStatus.running',
  completed: 'eval.runStatus.completed',
  failed: 'eval.runStatus.failed',
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
  items_unscorable: 'Items unscorable',
  items_failed: 'Items failed',
  mean_latency_ms: 'Mean retrieval latency',
}

export const CONFIG_SNAPSHOT_LABELS = {
  snapshot_version: 'Snapshot version',
  mode: 'Run mode',
  pipeline_mode: 'Pipeline',
  top_k_documents: 'Top-k documents',
  candidate_k: 'Candidate depth',
  context_k: 'Answer context depth',
  retrieval_strategy: 'Retrieval strategy',
  hybrid_search_active: 'Hybrid search active',
  hybrid_search_alpha_applied: 'Hybrid alpha applied',
  reranker_active: 'Reranker active',
  reranker_implementation: 'Reranker implementation',
  reranker_model: 'Reranker model',
  merge_kept_k: 'Merge kept-k',
  min_similarity_threshold_applied: 'Min similarity applied',
  pass_two_active: 'Pass two active',
  pass_two_chunk_threshold: 'Pass two chunk threshold',
  pass_two_score_threshold: 'Pass two score threshold',
  embedding_model: 'Embedding model',
  embedding_vector_size: 'Embedding vector size',
  vector_collection: 'Vector collection',
  chunk_strategy: 'Chunk strategy',
  chunk_size: 'Chunk size',
  chunk_overlap: 'Chunk overlap',
  // Only ever present on a snapshot stored before the effective-config
  // fields above replaced them. Kept so a historical run's diff reads as
  // something other than a raw key name.
  reranker_enabled: 'Reranker (legacy flag)',
  reranker_top_k: 'Reranker top-k (legacy flag)',
  hybrid_search_enabled: 'Hybrid search (legacy flag)',
  hybrid_search_alpha: 'Hybrid alpha (legacy flag)',
  min_similarity_threshold: 'Min similarity (legacy flag)',
}

export const EVAL_MODE_LABEL_KEYS = {
  retrieval: 'eval.mode.retrieval',
  end_to_end: 'eval.mode.endToEnd',
}

/** Said plainly before an end-to-end run, which is the one that spends money. */
export const EVAL_MODE_HELP_KEYS = {
  retrieval: 'eval.modeHelp.retrieval',
  end_to_end: 'eval.modeHelp.endToEnd',
}

/** Shown when the estimate covers a model with no configured price. */
export const UNPRICED_MODEL_NOTE_KEY = 'evalSingle.unpricedNote'

export const EVAL_ANSWER_METRIC_LABELS = {
  groundedness: 'Mean groundedness',
  hallucination_rate: 'Hallucination rate',
  hallucination_severe_rate: 'Severe hallucinations',
  citation_precision: 'Citation precision',
  citation_recall: 'Citation recall',
  unsupported_claims: 'Unsupported claims per answer',
  items_judged: 'Items judged',
}

/**
 * Stage-failure categories, in the order the backend ladder attributes them.
 *
 * The order is the pipeline's own, so reading the table top to bottom walks
 * an item from the index to the answer. The last three are not retrieval
 * failures and sit at the bottom for that reason: a stale label or a crashed
 * item above "never a candidate" would read as a retrieval regression.
 */
export const FAILURE_CATEGORY_ORDER = [
  'index',
  'retrieval',
  'pass_two',
  'ranking',
  'context',
  'completeness',
  'generation',
  'grounding',
  'stale_labels',
  'pipeline_error',
  'unclassified',
]

export const FAILURE_CATEGORY_LABEL_KEYS = {
  index: 'evalFailure.index',
  retrieval: 'evalFailure.retrieval',
  pass_two: 'evalFailure.passTwo',
  ranking: 'evalFailure.ranking',
  context: 'evalFailure.context',
  completeness: 'evalFailure.completeness',
  generation: 'evalFailure.generation',
  grounding: 'evalFailure.grounding',
  stale_labels: 'evalFailure.staleLabels',
  pipeline_error: 'evalFailure.pipelineError',
  unclassified: 'evalFailure.unclassified',
}

/** What each category means, and therefore which knob it points at. */
export const FAILURE_CATEGORY_HELP_KEYS = {
  index: 'evalFailureHelp.index',
  retrieval: 'evalFailureHelp.retrieval',
  pass_two: 'evalFailureHelp.passTwo',
  ranking: 'evalFailureHelp.ranking',
  context: 'evalFailureHelp.context',
  completeness: 'evalFailureHelp.completeness',
  generation: 'evalFailureHelp.generation',
  grounding: 'evalFailureHelp.grounding',
  stale_labels: 'evalFailureHelp.staleLabels',
  pipeline_error: 'evalFailureHelp.pipelineError',
  unclassified: 'evalFailureHelp.unclassified',
}

/** Shown above the attribution table. */
export const FAILURE_ATTRIBUTION_NOTE_KEY = 'evalNote.failureAttribution'

/** Shown when a run scored items but attributed none of them to a failure. */
export const NO_FAILURES_NOTE_KEY = 'evalNote.noFailures'

export const MATCH_MODE_LABEL_KEYS = {
  chunk_id: 'evalMatchMode.chunk',
  file_id: 'evalMatchMode.file',
  mixed: 'evalMatchMode.mixed',
}

/** Shown whenever the two most recent runs ran under different settings. */
export const CONFIG_DIFF_NOTE_KEY = 'evalNote.configDiff'

/** Shown for snapshot fields the rag service cannot observe. */
export const UNOBSERVED_NOTE_KEY = 'evalNote.unobserved'

/** Shown beside file-level runs, which score more generously than chunk-level. */
export const FILE_MATCH_NOTE_KEY = 'evalNote.fileMatch'

/** The empty state's explainer. A golden set is hand-built, and saying so is
 *  more useful than a button that implies otherwise. */
export const GOLDEN_SET_HELP_KEYS = [
  'eval.goldenSetStep1',
  'eval.goldenSetStep2',
  'eval.goldenSetStep3',
]

/** How many hex characters of a dataset fingerprint the UI shows. */
export const FINGERPRINT_PREFIX = 12

/**
 * A dataset fingerprint, abbreviated for display.
 *
 * Twelve hex characters is plenty to tell two label sets apart by eye, which
 * is all this is for; the full digest stays in the element's title so it can
 * still be copied and compared exactly.
 */
export function formatFingerprint(sha) {
  if (!sha) return EMPTY
  return String(sha).slice(0, FINGERPRINT_PREFIX)
}

/** Shown for a run recorded before datasets carried a version. */
export const UNVERSIONED_RUN_NOTE_KEY = 'evalNote.unversionedRun'

/** Shown when the dataset has been edited since the displayed run. */
export const DATASET_DRIFT_NOTE_KEY = 'evalNote.datasetDrift'

// ---------------------------------------------------------------------------
// Golden-set label validation
// ---------------------------------------------------------------------------

/**
 * The distinction the whole feature exists to draw.
 *
 * A retrieval miss means the retriever failed to rank a chunk that is there.
 * A stale label means the chunk is not there at all, so nothing the
 * retriever could have done would have found it. They look identical on a
 * recall chart and mean opposite things about the system.
 */
export const STALE_LABEL_NOTE_KEY = 'evalNote.staleLabel'

/** Shown for labels that still exist but retrieval is not allowed to return. */
export const UNRETRIEVABLE_LABEL_NOTE_KEY = 'evalNote.unretrievableLabel'

/** Shown when a run scored without its labels having been verified. */
export const UNCHECKED_LABELS_NOTE_KEY = 'evalNote.uncheckedLabels'

/** Why a run's labels were not verified. Keyed by the stored `reason`. */
export const LABEL_CHECK_REASON_KEYS = {
  disabled: 'evalNote.checkReason.disabled',
  no_labels: 'evalNote.checkReason.noLabels',
  unavailable: 'evalNote.checkReason.unavailable',
}

/** Shown on the per-item row of an item excluded for stale labels. */
export const UNSCORABLE_ITEM_NOTE_KEY = 'evalNote.unscorableItem'

/** Confirmation that a run's ground truth was checked and held up. */
export const LABELS_VERIFIED_NOTE_KEY = 'evalNote.labelsVerified'

/** How many affected ids one warning card lists before it stops. */
export const MAX_STALE_IDS_SHOWN = 12

/**
 * Render a boolean setting as a word rather than "true"/"false".
 *
 * Any other value is a configuration value — a model id, a number, a
 * strategy name — and is shown exactly as stored.
 */
export function formatSetting(value, t) {
  if (value === null || value === undefined || value === '') return EMPTY
  if (typeof value === 'boolean') {
    const key = value ? 'evalReport.on' : 'evalReport.off'
    return t ? t(key) : translate(DEFAULT_LOCALE, key)
  }
  return String(value)
}
