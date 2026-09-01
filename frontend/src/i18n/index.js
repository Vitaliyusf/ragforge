/** Interface localization: one import point for the whole application. */

export { I18nProvider, useI18n } from './I18nContext'
export { MESSAGES, interpolate, translate } from './translate'
export {
  DEFAULT_LOCALE,
  LOCALES,
  LOCALE_CODES,
  LOCALE_COOKIE,
  LOCALE_COOKIE_MAX_AGE,
  LOCALE_DIRECTION,
  LOCALE_NAMES,
  directionForLocale,
  isSupportedLocale,
  localeCookieValue,
  normalizeLocale,
  readLocaleCookie,
  readLocaleFromCookieString,
  writeLocaleCookie,
} from './locale'
