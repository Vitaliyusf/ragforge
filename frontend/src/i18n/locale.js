/**
 * Interface locale: the direction and language of the application *chrome*.
 *
 * This is deliberately a different question from the one
 * `lib/accessibility/direction.js` answers. That module decides which way a
 * given run of *user-generated* text reads — a Hebrew answer inside an English
 * shell still reads right-to-left. This module decides which way the shell
 * itself reads. Merging the two would force an English answer into RTL the
 * moment a reader switched the interface to Hebrew, which is wrong.
 *
 * Persistence is a cookie rather than localStorage so the *server* render can
 * read it: the root layout stamps `lang`/`dir` on <html> from this cookie, and
 * a client-only store would leave every refresh flashing LTR before correcting
 * itself. Nothing user-identifying goes in it — it holds `en` or `he`.
 */

export const LOCALES = Object.freeze(['en', 'he'])

export const DEFAULT_LOCALE = 'en'

/** RagForge is a public engineering portfolio; English is the safe default. */
export const LOCALE_COOKIE = 'ragforge-locale'

/** One year. Long enough that a returning reader keeps their choice. */
export const LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365

export const LOCALE_DIRECTION = Object.freeze({
  en: 'ltr',
  he: 'rtl',
})

/** Display names, each written in its own language. */
export const LOCALE_NAMES = Object.freeze({
  en: 'English',
  he: 'עברית',
})

/** Compact codes for the secondary line of the language menu. */
export const LOCALE_CODES = Object.freeze({
  en: 'EN',
  he: 'HE',
})

/**
 * @param {*} value
 * @returns {boolean} whether the value is a locale this build supports.
 */
export function isSupportedLocale(value) {
  return typeof value === 'string' && LOCALES.includes(value)
}

/**
 * Coerce anything — a cookie value, a prop, a stale persisted string — into a
 * locale this build can render. Never throws, never returns undefined.
 * @param {*} value
 * @returns {'en'|'he'}
 */
export function normalizeLocale(value) {
  return isSupportedLocale(value) ? value : DEFAULT_LOCALE
}

/**
 * @param {*} locale
 * @returns {'ltr'|'rtl'}
 */
export function directionForLocale(locale) {
  return LOCALE_DIRECTION[normalizeLocale(locale)]
}

/**
 * Read the locale out of a raw `document.cookie`-shaped string.
 *
 * Kept pure and string-in/string-out so both the browser and a test can use
 * it without a DOM.
 * @param {string} cookieHeader
 * @returns {'en'|'he'}
 */
export function readLocaleFromCookieString(cookieHeader) {
  if (typeof cookieHeader !== 'string' || !cookieHeader) return DEFAULT_LOCALE
  for (const part of cookieHeader.split(';')) {
    const [name, ...rest] = part.split('=')
    if (name.trim() === LOCALE_COOKIE) {
      return normalizeLocale(decodeURIComponent(rest.join('=').trim()))
    }
  }
  return DEFAULT_LOCALE
}

/** The locale the browser currently has persisted, or the default. */
export function readLocaleCookie() {
  if (typeof document === 'undefined') return DEFAULT_LOCALE
  return readLocaleFromCookieString(document.cookie)
}

/**
 * The exact `Set-Cookie`-style value written for a locale.
 *
 * `SameSite=Lax` and no `Secure` flag: this is a display preference, it must
 * survive a plain-HTTP deployment, and it carries nothing worth protecting.
 * @param {'en'|'he'} locale
 * @returns {string}
 */
export function localeCookieValue(locale) {
  return `${LOCALE_COOKIE}=${normalizeLocale(locale)}; Path=/; Max-Age=${LOCALE_COOKIE_MAX_AGE}; SameSite=Lax`
}

/** Persist the locale for the next server render. No-op outside a browser. */
export function writeLocaleCookie(locale) {
  if (typeof document === 'undefined') return
  document.cookie = localeCookieValue(locale)
}
