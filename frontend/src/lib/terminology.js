/**
 * One canonical label per product concept.
 *
 * Before this module the same thing had several names depending on which
 * surface you were looking at: "Files" in the nav, "Knowledge files" in the
 * chat placeholder, "Document library" in copy; "Rag" in one label table and
 * "RAG Orchestrator" in another; "Vector Db" and "Vector DB".
 *
 * The rule this file encodes: a *product destination* and a *backend service*
 * are different concepts and keep different names. `files` the deployable
 * service is "File Service"; the place a user manages their documents is
 * "Knowledge". Both are correct, and neither is allowed a second spelling.
 */

/** Deployable services, as named in health, metrics and log surfaces. */
export const SERVICE_LABELS = Object.freeze({
  gateway: 'Gateway',
  llm_agent: 'LLM Agent',
  embedding: 'Embedding',
  reranker: 'Reranker',
  rag: 'RAG Orchestrator',
  files: 'File Service',
  vector_db: 'Vector DB',
  memory: 'Memory',
})

/**
 * @param {string} name backend service key
 * @returns {string} the canonical display name, or the raw key if unknown —
 *   an unknown service is still worth showing, just not worth inventing a
 *   pretty name for.
 */
export function serviceLabel(name) {
  return SERVICE_LABELS[name] || name
}

/** Product concepts, as named in navigation, headings and body copy. */
export const PRODUCT_LABELS = Object.freeze({
  knowledge: 'Knowledge',
  chat: 'Chat',
  eval: 'Eval',
  metrics: 'Metrics',
  models: 'Models',
  logs: 'Logs',
  health: 'Health',
  users: 'Users',
  settings: 'Settings',
  memory: 'Memory',
  upload: 'Upload',
  training: 'Training',
})
