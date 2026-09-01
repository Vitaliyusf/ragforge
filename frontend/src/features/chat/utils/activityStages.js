/**
 * Graph node names → the one sentence a reader should see while waiting.
 *
 * The RAG service emits a `status` event with the real node name on every node
 * entry and exit, for every answer mode, so this is a translation of work that
 * actually happened — never a simulated progress animation. A node with no
 * entry here yields the generic label, and the terminal node yields `null` so
 * the indicator disappears rather than inventing a final step.
 *
 * The node names on the left are the backend's and are never translated. What
 * a stage is *called* to a reader is a translation key, resolved by the
 * component; `label` stays the canonical English so this module remains pure
 * and testable without a locale.
 */

import { DEFAULT_LOCALE } from '@/i18n/locale'
import { translate } from '@/i18n/translate'

const STAGE_LABEL_KEY = {
  load_history: 'chat.stage.recalling',
  load_memory_light: 'chat.stage.recalling',
  load_memory_deep: 'chat.stage.recalling',
  input_guardrails: 'chat.stage.checkingRequest',
  output_guardrails: 'chat.stage.checkingAnswer',
  rewrite_query: 'chat.stage.refining',
  query_rewrite: 'chat.stage.refining',
  retrieve_chunks_once: 'chat.stage.retrieving',
  retrieve_pass_one: 'chat.stage.retrieving',
  retrieve_pass_two_if_needed: 'chat.stage.retrievingMore',
  rerank_and_merge: 'chat.stage.reranking',
  generate_answer: 'chat.stage.generating',
  generate_draft_answer: 'chat.stage.generating',
  evaluate_answer_light: 'chat.stage.reviewing',
  evaluate_answer_deep: 'chat.stage.reviewing',
  revise_once_if_needed: 'chat.stage.revising',
  persist_turn: 'chat.stage.saving',
}

const GENERIC_LABEL_KEY = 'chat.stage.working'
const TERMINAL_NODES = new Set(['stream_done'])

/**
 * Describe the live execution stage for the message list.
 *
 * @param {{node?: string, phase?: string, progress?: number}|null} status
 *   The latest `status` event payload for the active turn.
 * @returns {{label: string, labelKey: string, progress: number|null}|null}
 *   `null` when there is nothing truthful to show.
 */
export function describeStage(status) {
  if (!status) return null
  const node = status.node
  if (node && TERMINAL_NODES.has(node)) return null
  const labelKey = (node && STAGE_LABEL_KEY[node]) || GENERIC_LABEL_KEY
  return {
    label: translate(DEFAULT_LOCALE, labelKey),
    labelKey,
    // Unknown progress stays null: a bar is only drawn for a number the
    // backend actually reported.
    progress: Number.isFinite(status.progress) ? status.progress : null,
  }
}

export { STAGE_LABEL_KEY, GENERIC_LABEL_KEY }
