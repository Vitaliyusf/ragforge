/** Root layout */
import { cookies } from 'next/headers'
import { GeistSans } from 'geist/font/sans'
import { GeistMono } from 'geist/font/mono'
import { Providers } from '@/components/Providers'
import { LOCALE_COOKIE, directionForLocale, normalizeLocale } from '@/i18n/locale'
import { translate } from '@/i18n/translate'
import '@/styles/globals.css'

export const metadata = {
  title: 'RAGForge',
  description: 'AI Operations Platform',
}

/**
 * `lang` and `dir` are decided on the server, from the persisted locale.
 *
 * Deriving them in an Effect instead would paint every Hebrew session
 * left-to-right for one frame after each refresh and then jump — the whole
 * shell mirrors, so that flash is the entire layout moving. Reading the cookie
 * here costs one synchronous lookup and removes the flash outright.
 *
 * `suppressHydrationWarning` stays: theme and other persisted UI preferences
 * legitimately change the client's first render.
 */
export default async function RootLayout({ children }) {
  const cookieStore = await cookies()
  const locale = normalizeLocale(cookieStore.get(LOCALE_COOKIE)?.value)
  const direction = directionForLocale(locale)

  return (
    <html
      lang={locale}
      dir={direction}
      suppressHydrationWarning
      className={`${GeistSans.variable} ${GeistMono.variable}`}
    >
      <body className="font-sans antialiased" style={{ background: 'var(--bg)', color: 'var(--fg)' }}>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:inset-s-4 focus:z-[9999] focus:px-4 focus:py-2 focus:rounded-lg focus:text-white focus:outline-hidden"
          style={{ background: 'var(--primary)' }}
        >
          {translate(locale, 'nav.skipToContent')}
        </a>
        {/* The Toaster moved inside Providers: its anchor edge and text
            direction follow the interface locale, which only the client
            context knows after a switch. */}
        <Providers initialLocale={locale}>{children}</Providers>
      </body>
    </html>
  )
}
