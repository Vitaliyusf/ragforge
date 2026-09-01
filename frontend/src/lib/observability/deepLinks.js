/**
 * Cross-screen deep links, built in one place.
 *
 * An operational workflow is only inspectable if the identifier on the screen
 * you are looking at opens the screen that explains it. Every such jump used
 * to be either absent or hand-rolled at the call site, which meant each one
 * decided for itself what counted as a usable identifier.
 *
 * Two rules keep these honest:
 *
 * - **A builder returns `null` when there is no real identifier.** A dead
 *   button that lands on an unfiltered page teaches the operator that the
 *   link means nothing. No identifier, no link.
 * - **A link never claims more than it does.** The log jumps are a substring
 *   filter over the lines the services still hold, not a trace store lookup,
 *   and their `title` says exactly that. There is no trace-store contract
 *   behind them to pretend otherwise with.
 *
 * Each descriptor carries both the canonical English `label`/`title` and the
 * `labelKey`/`titleKey` that render them in the reader's language. This module
 * is pure — it has no React context and therefore no locale — so the component
 * that draws the button is what resolves the keys.
 */

import { serviceLabel } from '@/lib/terminology'
import { DEFAULT_LOCALE } from '@/i18n/locale'
import { translate } from '@/i18n/translate'

/** Services whose output the log route will serve. Mirrors `log_services`. */
export const LOG_SERVICES = Object.freeze([
  'gateway',
  'files',
  'embedding',
  'llm_agent',
  'memory',
  'rag',
  'reranker',
  'vector_db',
])

/** Every severity the log viewer knows, which is also "no severity filter". */
export const LOG_SEVERITIES = Object.freeze([
  'error',
  'warning',
  'info',
  'debug',
  'trace',
  'unknown',
])

export const DEEP_LINK_KIND = Object.freeze({
  LOGS: 'logs',
  CONVERSATION: 'conversation',
  DOCUMENT: 'document',
})

/**
 * A zero-filled or dashed UUID is a placeholder the backend never filled in.
 * Linking on one produces a filter that matches every unfilled id in the
 * stream, which is worse than no link at all.
 */
const PLACEHOLDER_ID = /^[0-]+$/

/**
 * @param {*} value
 * @returns {boolean} whether this is an identifier worth linking on.
 */
export function isUsableIdentifier(value) {
  if (value == null) return false
  const text = String(value).trim()
  return text !== '' && !PLACEHOLDER_ID.test(text)
}

const LOG_SEARCH_CAVEAT = translate(DEFAULT_LOCALE, 'deepLink.logsCaveat')

/**
 * Open the log stream filtered to one correlation identifier.
 *
 * @param {object} options
 * @param {?string} options.id a trace, request, turn or correlation id
 * @param {string} [options.kindLabel] what the id identifies, for the label
 * @param {string[]} [options.services] services to search, defaulting to all
 * @returns {?object} a link descriptor, or null when the id is unusable
 */
export function logsLinkForCorrelation({ id, kindLabel = 'trace', services } = {}) {
  if (!isUsableIdentifier(id)) return null
  const text = String(id).trim()
  const scoped = (services || LOG_SERVICES).filter((name) => LOG_SERVICES.includes(name))
  return {
    kind: DEEP_LINK_KIND.LOGS,
    destination: 'logs',
    label: translate(DEFAULT_LOCALE, 'deepLink.findInLogs'),
    labelKey: 'deepLink.findInLogs',
    title: translate(DEFAULT_LOCALE, 'deepLink.findInLogsTitle', {
      kind: kindLabel,
      caveat: LOG_SEARCH_CAVEAT,
    }),
    titleKey: 'deepLink.findInLogsTitle',
    titleVars: { kind: kindLabel, caveatKey: 'deepLink.logsCaveat' },
    logs: {
      textFilter: text,
      services: scoped.length ? scoped : [...LOG_SERVICES],
      severities: [...LOG_SEVERITIES],
    },
  }
}

/**
 * Open the log stream for one service, narrowed to what went wrong.
 *
 * Used from Health, where the question a degraded service raises is always
 * "what is it saying?" — so this drops the quieter severities rather than
 * landing the operator in an undifferentiated stream.
 *
 * @param {?string} service backend service key
 * @returns {?object}
 */
export function logsLinkForService(service) {
  if (!LOG_SERVICES.includes(service)) return null
  return {
    kind: DEEP_LINK_KIND.LOGS,
    destination: 'logs',
    label: translate(DEFAULT_LOCALE, 'deepLink.viewLogs'),
    labelKey: 'deepLink.viewLogs',
    title: translate(DEFAULT_LOCALE, 'deepLink.viewLogsTitle', { service: serviceLabel(service) }),
    titleKey: 'deepLink.viewLogsTitle',
    // Service display names are canonical and stay English in both locales.
    titleVars: { service: serviceLabel(service) },
    logs: {
      textFilter: '',
      services: [service],
      severities: ['error', 'warning'],
    },
  }
}

/**
 * Open the conversation a recorded turn belongs to.
 *
 * The metrics store records the same conversation id the chat route is keyed
 * by, so this is a real jump rather than a search.
 *
 * @param {?string} conversationId
 * @returns {?object}
 */
export function conversationLink(conversationId) {
  if (!isUsableIdentifier(conversationId)) return null
  const id = String(conversationId).trim()
  return {
    kind: DEEP_LINK_KIND.CONVERSATION,
    destination: 'chat',
    label: translate(DEFAULT_LOCALE, 'deepLink.openInChat'),
    labelKey: 'deepLink.openInChat',
    title: translate(DEFAULT_LOCALE, 'deepLink.openInChatTitle'),
    titleKey: 'deepLink.openInChatTitle',
    route: `/chat/${encodeURIComponent(id)}`,
  }
}

/**
 * Open the document library filtered to one file.
 *
 * @param {?string} fileId
 * @param {?string} [filename] shown in the tooltip when the id is opaque
 * @returns {?object}
 */
export function documentLink(fileId, filename = null) {
  if (!isUsableIdentifier(fileId)) return null
  const id = String(fileId).trim()
  return {
    kind: DEEP_LINK_KIND.DOCUMENT,
    destination: 'files',
    label: translate(DEFAULT_LOCALE, 'deepLink.openInKnowledge'),
    labelKey: 'deepLink.openInKnowledge',
    title: filename
      ? translate(DEFAULT_LOCALE, 'deepLink.openInKnowledgeNamedTitle', { filename })
      : translate(DEFAULT_LOCALE, 'deepLink.openInKnowledgeTitle'),
    titleKey: filename ? 'deepLink.openInKnowledgeNamedTitle' : 'deepLink.openInKnowledgeTitle',
    ...(filename ? { titleVars: { filename } } : {}),
    intent: { kind: DEEP_LINK_KIND.DOCUMENT, query: id },
  }
}
