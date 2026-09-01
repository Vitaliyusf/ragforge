'use client'

import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import {
  DEFAULT_LOCALE,
  directionForLocale,
  isSupportedLocale,
  normalizeLocale,
  writeLocaleCookie,
} from './locale'
import { translate } from './translate'

const I18nContext = createContext(null)

/**
 * Interface locale for the whole application shell.
 *
 * `initialLocale` comes from the server, which read the `ragforge-locale`
 * cookie in the root layout. Seeding state from it rather than discovering the
 * cookie in an Effect is what stops a Hebrew session painting LTR for one
 * frame after every refresh.
 *
 * The provider sits above the authentication gate on purpose: a reader who
 * cannot yet sign in still has to be able to read the sign-in form.
 */
export function I18nProvider({ children, initialLocale = DEFAULT_LOCALE }) {
  const [locale, setLocaleState] = useState(() => normalizeLocale(initialLocale))

  const setLocale = useCallback((nextLocale) => {
    if (!isSupportedLocale(nextLocale)) {
      if (process.env.NODE_ENV !== 'production') {
        console.warn(`[i18n] ignoring unsupported locale "${nextLocale}"`)
      }
      return
    }
    setLocaleState(nextLocale)
    writeLocaleCookie(nextLocale)
    // The root element was server-rendered with the previous locale's
    // attributes, so the switch updates them directly rather than waiting for
    // a navigation to re-run the layout. No reload: the whole point of the
    // control is that the shell flips in place.
    if (typeof document !== 'undefined') {
      document.documentElement.lang = nextLocale
      document.documentElement.dir = directionForLocale(nextLocale)
    }
  }, [])

  const value = useMemo(() => {
    const direction = directionForLocale(locale)
    return {
      locale,
      direction,
      isRTL: direction === 'rtl',
      setLocale,
      t: (key, variables) => translate(locale, key, variables),
    }
  }, [locale, setLocale])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

/**
 * The context a component gets when it is rendered outside a provider.
 *
 * Frozen at module scope rather than rebuilt per call: `t` ends up in the
 * dependency array of effects and callbacks, and a fresh identity on every
 * render would re-run every one of them — a component that loads on mount
 * would fetch in a loop. Provider-supplied `t` is memoised for the same
 * reason.
 */
const FALLBACK_CONTEXT = Object.freeze({
  locale: DEFAULT_LOCALE,
  direction: directionForLocale(DEFAULT_LOCALE),
  isRTL: false,
  setLocale: () => {},
  t: (key, variables) => translate(DEFAULT_LOCALE, key, variables),
})

/**
 * @returns {{locale: 'en'|'he', direction: 'ltr'|'rtl', isRTL: boolean,
 *   setLocale: (locale: string) => void, t: (key: string, vars?: object) => string}}
 *
 * Outside a provider this returns a working English context rather than
 * throwing: a component rendered in isolation by a test, or one mounted above
 * the provider by an error boundary, should still be readable.
 */
export function useI18n() {
  return useContext(I18nContext) ?? FALLBACK_CONTEXT
}
