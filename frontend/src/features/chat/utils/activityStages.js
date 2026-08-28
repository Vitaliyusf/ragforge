/**
 * Graph node names → the one sentence a reader should see while waiting.
 *
 * The RAG service emits a `status` event with the real node name on every node
 * entry and exit, for every answer mode, so this is a translation of work that
 * actually happened — never a simulated progress animation. A node with no
 * entry here yields the generic label, and the terminal node yields `null` so
 * the indicator disappears rather than inventing a final step.
 */

const STAGE_LABEL = {
  load_history: 'Recalling this conversation…',
  load_memory_light: 'Recalling this conversation…',
  load_memory_deep: 'Recalling this conversation…',
  input_guardrails: 'Checking the request…',
  output_guardrails: 'Checking the answer…',
  rewrite_query: 'Refining the question…',
  query_rewrite: 'Refining the question…',
  retrieve_chunks_once: 'Retrieving sources…',
  retrieve_pass_one: 'Retrieving sources…',
  retrieve_pass_two_if_needed: 'Retrieving more sources…',
  rerank_and_merge: 'Reranking…',
  generate_answer: 'Generating answer…',
  generate_draft_answer: 'Generating answer…',
  evaluate_answer_light: 'Reviewing…',
  evaluate_answer_deep: 'Reviewing…',
  revise_once_if_needed: 'Revising the answer…',
  persist_turn: 'Saving…',
}

const GENERIC_LABEL = 'Working…'
const TERMINAL_NODES = new Set(['stream_done'])

/**
 * Describe the live execution stage for the message list.
 *
 * @param {{node?: string, phase?: string, progress?: number}|null} status
 *   The latest `status` event payload for the active turn.
 * @returns {{label: string, progress: number|null}|null}
 *   `null` when there is nothing truthful to show.
 */
export function describeStage(status) {
  if (!status) return null
  const node = status.node
  if (node && TERMINAL_NODES.has(node)) return null
  return {
    label: (node && STAGE_LABEL[node]) || GENERIC_LABEL,
    // Unknown progress stays null: a bar is only drawn for a number the
    // backend actually reported.
    progress: Number.isFinite(status.progress) ? status.progress : null,
  }
}

export { STAGE_LABEL, GENERIC_LABEL }
