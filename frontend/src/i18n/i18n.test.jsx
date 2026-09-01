import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { I18nProvider, useI18n } from './I18nContext'
import { MESSAGES, interpolate, translate } from './translate'
import {
  DEFAULT_LOCALE,
  LOCALE_COOKIE,
  directionForLocale,
  localeCookieValue,
  normalizeLocale,
  readLocaleFromCookieString,
} from './locale'

function clearLocaleCookie() {
  document.cookie = `${LOCALE_COOKIE}=; Path=/; Max-Age=0`
}

function Probe() {
  const { locale, direction, isRTL, setLocale, t } = useI18n()
  return (
    <div>
      <span data-testid="locale">{locale}</span>
      <span data-testid="direction">{direction}</span>
      <span data-testid="rtl">{String(isRTL)}</span>
      <span data-testid="nav">{t('nav.chat')}</span>
      <span data-testid="count">{t('chat.messageCount', { count: 3 })}</span>
      <button type="button" onClick={() => setLocale('he')}>to-he</button>
      <button type="button" onClick={() => setLocale('en')}>to-en</button>
      <button type="button" onClick={() => setLocale('fr')}>to-fr</button>
    </div>
  )
}

describe('dictionary parity', () => {
  it('en and he carry exactly the same key set', () => {
    const enKeys = Object.keys(MESSAGES.en).sort()
    const heKeys = Object.keys(MESSAGES.he).sort()

    // Reported as set differences rather than as an equality failure: a bare
    // "arrays differ" tells you nothing about which key went missing.
    const missingInHe = enKeys.filter((key) => !(key in MESSAGES.he))
    const missingInEn = heKeys.filter((key) => !(key in MESSAGES.en))

    expect(missingInHe).toEqual([])
    expect(missingInEn).toEqual([])
    expect(heKeys).toEqual(enKeys)
  })

  it('no message is empty or non-string in either language', () => {
    for (const [locale, table] of Object.entries(MESSAGES)) {
      for (const [key, value] of Object.entries(table)) {
        expect(typeof value, `${locale}.${key}`).toBe('string')
        expect(value.trim(), `${locale}.${key}`).not.toBe('')
      }
    }
  })

  it('every placeholder in an English message also appears in the Hebrew one', () => {
    const placeholders = (value) => (value.match(/\{(\w+)\}/g) || []).sort()
    for (const key of Object.keys(MESSAGES.en)) {
      expect(placeholders(MESSAGES.he[key]), key).toEqual(placeholders(MESSAGES.en[key]))
    }
  })
})

describe('locale helpers', () => {
  it('normalizes unknown values to English', () => {
    expect(normalizeLocale('he')).toBe('he')
    expect(normalizeLocale('en')).toBe('en')
    expect(normalizeLocale('fr')).toBe('en')
    expect(normalizeLocale(undefined)).toBe('en')
    expect(normalizeLocale(null)).toBe('en')
  })

  it('maps locale to document direction', () => {
    expect(directionForLocale('en')).toBe('ltr')
    expect(directionForLocale('he')).toBe('rtl')
    expect(directionForLocale('zz')).toBe('ltr')
  })

  it('reads the locale out of a cookie header, ignoring other cookies', () => {
    expect(readLocaleFromCookieString('theme=dark; ragforge-locale=he; x=1')).toBe('he')
    expect(readLocaleFromCookieString('theme=dark')).toBe('en')
    expect(readLocaleFromCookieString('ragforge-locale=klingon')).toBe('en')
    expect(readLocaleFromCookieString('')).toBe('en')
  })

  it('writes a root-scoped, year-long, Lax cookie', () => {
    const value = localeCookieValue('he')
    expect(value).toContain('ragforge-locale=he')
    expect(value).toContain('Path=/')
    expect(value).toContain('SameSite=Lax')
    expect(value).toContain(`Max-Age=${60 * 60 * 24 * 365}`)
  })
})

describe('translate', () => {
  it('interpolates named variables', () => {
    expect(interpolate('Sources: {count}', { count: 2 })).toBe('Sources: 2')
    expect(translate('en', 'chat.messageCount', { count: 7 })).toBe('Messages in this thread: 7')
    expect(translate('he', 'chat.messageCount', { count: 7 })).toBe('הודעות בשיחה: 7')
  })

  it('leaves an unsupplied placeholder visible rather than rendering undefined', () => {
    expect(translate('en', 'chat.messageCount')).toBe('Messages in this thread: {count}')
    expect(translate('en', 'chat.messageCount', {})).toContain('{count}')
  })

  it('falls back to English when a Hebrew key is absent', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const original = MESSAGES.he['nav.chat']
    delete MESSAGES.he['nav.chat']
    try {
      expect(translate('he', 'nav.chat')).toBe('Chat')
    } finally {
      MESSAGES.he['nav.chat'] = original
      warn.mockRestore()
    }
  })

  it('never renders undefined for a key that exists in neither language', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(translate('he', 'does.not.exist')).toBe('does.not.exist')
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})

describe('I18nProvider', () => {
  beforeEach(() => {
    clearLocaleCookie()
    document.documentElement.lang = 'en'
    document.documentElement.dir = 'ltr'
  })

  it('defaults to English for a first-time visitor', () => {
    render(<I18nProvider><Probe /></I18nProvider>)
    expect(screen.getByTestId('locale')).toHaveTextContent(DEFAULT_LOCALE)
    expect(screen.getByTestId('direction')).toHaveTextContent('ltr')
    expect(screen.getByTestId('rtl')).toHaveTextContent('false')
    expect(screen.getByTestId('nav')).toHaveTextContent('Chat')
  })

  it('honours the locale the server resolved from the cookie', () => {
    render(<I18nProvider initialLocale="he"><Probe /></I18nProvider>)
    expect(screen.getByTestId('locale')).toHaveTextContent('he')
    expect(screen.getByTestId('direction')).toHaveTextContent('rtl')
    expect(screen.getByTestId('nav')).toHaveTextContent('צ׳אט')
  })

  it('switches language, direction, cookie and root attributes without a reload', async () => {
    const user = userEvent.setup()
    render(<I18nProvider><Probe /></I18nProvider>)

    await user.click(screen.getByRole('button', { name: 'to-he' }))

    expect(screen.getByTestId('locale')).toHaveTextContent('he')
    expect(screen.getByTestId('rtl')).toHaveTextContent('true')
    expect(screen.getByTestId('nav')).toHaveTextContent('צ׳אט')
    expect(document.documentElement.lang).toBe('he')
    expect(document.documentElement.dir).toBe('rtl')
    expect(document.cookie).toContain('ragforge-locale=he')

    await user.click(screen.getByRole('button', { name: 'to-en' }))
    expect(document.documentElement.dir).toBe('ltr')
    expect(document.cookie).toContain('ragforge-locale=en')
  })

  it('ignores an unsupported locale instead of blanking the interface', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const user = userEvent.setup()
    render(<I18nProvider initialLocale="he"><Probe /></I18nProvider>)

    await user.click(screen.getByRole('button', { name: 'to-fr' }))

    expect(screen.getByTestId('locale')).toHaveTextContent('he')
    warn.mockRestore()
  })

  it('normalizes a bad initial locale from the server', () => {
    render(<I18nProvider initialLocale="klingon"><Probe /></I18nProvider>)
    expect(screen.getByTestId('locale')).toHaveTextContent('en')
  })

  it('renders readable English outside a provider', () => {
    render(<Probe />)
    expect(screen.getByTestId('locale')).toHaveTextContent('en')
    expect(screen.getByTestId('nav')).toHaveTextContent('Chat')
  })
})
