import { DEEP_LINK_KIND } from './deepLinks'

/**
 * The one place a deep link is acted on.
 *
 * A plain factory rather than a hook: the shell owns the Redux store, the
 * router and the tab state, so it is the only thing that can perform a jump —
 * and a factory keeps every panel that *offers* a link free of all three. A
 * metrics table should not need a store mounted above it to render a button.
 *
 * @param {object} deps
 * @param {Function} deps.dispatch Redux dispatch
 * @param {{push: Function}} deps.router the App Router
 * @param {Function} deps.navigate `(destination, intent?) => void` from the shell
 * @param {object} deps.logActions the log slice's filter action creators
 * @returns {(link: ?object) => void}
 */
export function createDeepLinkFollower({ dispatch, router, navigate, logActions }) {
  return function followDeepLink(link) {
    if (!link) return
    switch (link.kind) {
      case DEEP_LINK_KIND.LOGS:
        // Filters go through the log viewer's own slice. It already reads
        // them from there, and a second channel into the same state is how
        // two sources of truth start.
        dispatch(logActions.setSelectedServices(link.logs.services))
        dispatch(logActions.setSeverityFilter(link.logs.severities))
        dispatch(logActions.setTextFilter(link.logs.textFilter))
        navigate(link.destination)
        break
      case DEEP_LINK_KIND.CONVERSATION:
        // ChatContext derives the open conversation from the pathname, so the
        // route move is what opens it; the tab switch only brings the right
        // workspace forward.
        router.push(link.route)
        navigate(link.destination)
        break
      case DEEP_LINK_KIND.DOCUMENT:
        navigate(link.destination, link.intent)
        break
      default:
        break
    }
  }
}
