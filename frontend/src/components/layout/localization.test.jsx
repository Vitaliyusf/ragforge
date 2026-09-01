/**
 * FRONT-I18N-01 — the shell in two languages.
 *
 * The failures this file exists to prevent are the ones a screenshot would
 * not show: an English label surviving in a Hebrew nav, a Hebrew label
 * leaking into an English one, a language switch quietly resetting the
 * theme, and a technical identifier being reordered by the bidi algorithm
 * the moment the interface turns RTL.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import Header from './Header'
import { I18nProvider } from '@/i18n'
import { LOCALE_COOKIE } from '@/i18n/locale'
import { MESSAGES } from '@/i18n/translate'

const toggleTheme = vi.fn()
const themeState = { resolvedTheme: 'dark' }

vi.mock('@/context/ThemeContext', () => ({
  useTheme: () => ({ resolvedTheme: themeState.resolvedTheme, toggleTheme }),
}))

vi.mock('@/features/auth', () => ({
  useAuth: () => ({
    user: { role: 'admin', email: 'operator@example.com', display_name: 'Operator' },
    isAdmin: true,
    logout: vi.fn(),
  }),
}))

vi.mock('@/features/config', () => ({
  configService: { getConfig: vi.fn().mockResolvedValue({ llm_implementation: 'vllm' }) },
}))

function renderHeader(locale = 'en') {
  return render(
    <I18nProvider initialLocale={locale}>
      <Header activeTab="chat" setActiveTab={vi.fn()} />
    </I18nProvider>
  )
}

/** Every Hebrew nav label the model can render, for leak checks. */
const HEBREW_NAV = Object.entries(MESSAGES.he)
  .filter(([key]) => key.startsWith('nav.') && !key.startsWith('nav.pillar'))
  .map(([, value]) => value)

const ENGLISH_NAV = Object.entries(MESSAGES.en)
  .filter(([key]) => key.startsWith('nav.') && !key.startsWith('nav.pillar'))
  .map(([, value]) => value)

beforeEach(() => {
  document.cookie = `${LOCALE_COOKIE}=; Path=/; Max-Age=0`
  document.documentElement.lang = 'en'
  document.documentElement.dir = 'ltr'
  themeState.resolvedTheme = 'dark'
})

describe('header navigation', () => {
  it('names every destination in English by default', () => {
    renderHeader('en')
    expect(screen.getByRole('button', { name: 'Chat' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Knowledge' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Settings' })).toBeInTheDocument()
  })

  it('names every destination in Hebrew when the interface is Hebrew', () => {
    renderHeader('he')
    expect(screen.getByRole('button', { name: 'צ׳אט' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'מאגר ידע' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'הגדרות' })).toBeInTheDocument()
  })

  it('leaves no English nav label in the Hebrew shell', () => {
    renderHeader('he')
    const nav = screen.getByRole('navigation')
    for (const label of ENGLISH_NAV) {
      // `Eval` and `Chat` are the risky ones: short words that a partial
      // migration would leave behind untranslated.
      expect(within(nav).queryByRole('button', { name: label })).toBeNull()
    }
  })

  it('leaves no Hebrew nav label in the English shell', () => {
    renderHeader('en')
    const nav = screen.getByRole('navigation')
    for (const label of HEBREW_NAV) {
      expect(within(nav).queryByRole('button', { name: label })).toBeNull()
    }
  })

  it('labels the pillars in the readers language', () => {
    renderHeader('he')
    expect(screen.getByRole('group', { name: 'סביבת עבודה' })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: 'ניהול' })).toBeInTheDocument()
  })
})

describe('language switcher', () => {
  it('is reachable by its accessible name in both languages', () => {
    const { unmount } = renderHeader('en')
    expect(screen.getByRole('button', { name: 'Change language' })).toBeInTheDocument()
    unmount()

    renderHeader('he')
    expect(screen.getByRole('button', { name: 'החלפת שפה' })).toBeInTheDocument()
  })

  it('offers each language written in its own script, and no flags', async () => {
    const user = userEvent.setup()
    renderHeader('en')
    await user.click(screen.getByRole('button', { name: 'Change language' }))

    const menu = screen.getByRole('menu')
    expect(within(menu).getByRole('menuitemradio', { name: /English/ })).toBeInTheDocument()
    expect(within(menu).getByRole('menuitemradio', { name: /עברית/ })).toBeInTheDocument()
    // A language is not a nationality: no flag emoji anywhere in the menu.
    expect(menu.textContent).not.toMatch(/\p{Regional_Indicator}/u)
  })

  it('switches the whole shell to Hebrew, and stamps the document with it', async () => {
    const user = userEvent.setup()
    renderHeader('en')

    await user.click(screen.getByRole('button', { name: 'Change language' }))
    await user.click(screen.getByRole('menuitemradio', { name: /עברית/ }))

    expect(screen.getByRole('button', { name: 'צ׳אט' })).toBeInTheDocument()
    expect(document.documentElement.lang).toBe('he')
    expect(document.documentElement.dir).toBe('rtl')
    expect(document.cookie).toContain('ragforge-locale=he')
  })

  it('closes the menu on selection and marks the active language', async () => {
    const user = userEvent.setup()
    renderHeader('he')

    await user.click(screen.getByRole('button', { name: 'החלפת שפה' }))
    expect(screen.getByRole('menuitemradio', { name: /עברית/ })).toHaveAttribute(
      'aria-checked',
      'true'
    )

    await user.click(screen.getByRole('menuitemradio', { name: /English/ }))
    expect(screen.queryByRole('menu')).toBeNull()
  })

  it('does not touch the theme when the language changes', async () => {
    const user = userEvent.setup()
    renderHeader('en')

    await user.click(screen.getByRole('button', { name: 'Change language' }))
    await user.click(screen.getByRole('menuitemradio', { name: /עברית/ }))

    // The two preferences are independent: switching one must not call the
    // other's setter, in either direction.
    expect(toggleTheme).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'מעבר למצב בהיר' })).toBeInTheDocument()
  })

  it('does not reset the language when the theme changes', async () => {
    const user = userEvent.setup()
    renderHeader('he')

    await user.click(screen.getByRole('button', { name: 'מעבר למצב בהיר' }))

    expect(toggleTheme).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'צ׳אט' })).toBeInTheDocument()
    // The theme toggle must not write the locale cookie: the only thing that
    // touches it is the language control.
    expect(document.cookie).not.toContain('ragforge-locale')
  })
})

describe('header chrome', () => {
  it('localizes the theme, sign-out and brand controls', () => {
    renderHeader('he')
    expect(screen.getByRole('button', { name: 'מעבר למצב בהיר' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'יציאה' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'מעבר לצ׳אט' })).toBeInTheDocument()
  })

  it('keeps the RAGForge wordmark left-to-right inside the Hebrew shell', () => {
    renderHeader('he')
    // The brand is a proper noun. An unisolated wordmark in an RTL run has
    // its two halves reordered, which is a different product name.
    const wordmark = screen.getByText('RAG').closest('span')
    expect(wordmark).toHaveAttribute('dir', 'ltr')
    expect(wordmark.className).toContain('unicode-bidi:isolate')
  })

  it('renders the Hebrew brand tagline without translating the brand itself', () => {
    renderHeader('he')
    expect(screen.getByText('סביבת עבודה ל-AI')).toBeInTheDocument()
    expect(screen.getByText('RAG')).toBeInTheDocument()
  })
})
