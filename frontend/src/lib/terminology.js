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

/**
 * Product concepts → the translation key that names them.
 *
 * The names themselves moved into `src/i18n/messages/*`. This table is what
 * stops them being re-spelled per surface: navigation, the activity popover
 * and any heading that needs a destination's name all resolve the same key,
 * so a rename lands everywhere at once and Hebrew cannot drift from English.
 *
 * Keys, not strings, because this module has no React context to read and
 * must stay callable from plain utilities — the component resolves the key at
 * render time, where the active locale is known.
 */
export const PRODUCT_LABEL_KEYS = Object.freeze({
  knowledge: 'nav.knowledge',
  chat: 'nav.chat',
  eval: 'nav.eval',
  metrics: 'nav.metrics',
  models: 'nav.models',
  logs: 'nav.logs',
  health: 'nav.health',
  users: 'nav.users',
  settings: 'nav.settings',
  memory: 'nav.memory',
  upload: 'nav.upload',
  training: 'nav.training',
})
