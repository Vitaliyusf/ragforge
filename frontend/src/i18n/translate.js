/**
 * Message lookup, deliberately free of React and of `'use client'`.
 *
 * The root layout is a server component and still has copy to render (the skip
 * link, the document title), so resolution has to be callable from both sides
 * of the boundary. Keeping it here rather than in `I18nContext.jsx` is what
 * makes that legal.
 */

import { en } from './messages/en'
import { he } from './messages/he'
import { DEFAULT_LOCALE } from './locale'

export const MESSAGES = { en, he }

const INTERPOLATION = /\{(\w+)\}/g

/**
 * Substitute `{name}` placeholders.
 *
 * A placeholder with no matching variable is left as written rather than
 * replaced with `undefined` — a visible `{count}` is a bug report; the string
 * "undefined" in the middle of a sentence is a mystery.
 *
 * @param {string} template
 * @param {Record<string, unknown>} [variables]
 * @returns {string}
 */
export function interpolate(template, variables) {
  if (!variables) return template
  return template.replace(INTERPOLATION, (match, name) =>
    (Object.prototype.hasOwnProperty.call(variables, name) && variables[name] != null
      ? String(variables[name])
      : match)
  )
}

/**
 * Resolve one key against a locale, falling back to English and then to the
 * key itself.
 *
 * The English fallback matters because the two dictionaries are enforced equal
 * by a test but a hand-edit can still land between test runs: a Hebrew reader
 * seeing an English label has lost a translation, whereas one seeing
 * `undefined` has lost the control.
 *
 * @param {'en'|'he'} locale
 * @param {string} key
 * @param {Record<string, unknown>} [variables]
 * @returns {string} never `undefined`, in any environment.
 */
export function translate(locale, key, variables) {
  const table = MESSAGES[locale] || MESSAGES[DEFAULT_LOCALE]
  let message = table[key]

  if (message == null && locale !== DEFAULT_LOCALE) {
    message = MESSAGES[DEFAULT_LOCALE][key]
  }

  if (message == null) {
    if (process.env.NODE_ENV !== 'production') {
      console.warn(`[i18n] missing message for key "${key}" (locale: ${locale})`)
    }
    // Never `undefined` on screen. The key is at least diagnosable.
    return interpolate(key, variables)
  }

  return interpolate(message, variables)
}
