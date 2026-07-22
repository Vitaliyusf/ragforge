/** Root layout */
import { GeistSans } from 'geist/font/sans'
import { GeistMono } from 'geist/font/mono'
import { Providers } from '@/components/Providers'
import { Toaster } from 'sonner'
import '@/styles/globals.css'

export const metadata = {
  title: 'RAGForge',
  description: 'AI Operations Platform',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="font-sans antialiased" style={{ background: 'var(--bg)', color: 'var(--fg)' }}>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-[9999] focus:px-4 focus:py-2 focus:rounded-lg focus:text-white focus:outline-none"
          style={{ background: 'var(--primary)' }}
        >
          Skip to main content
        </a>
        <Providers>
          {children}
          <Toaster
            position="top-right"
            richColors
            closeButton
            toastOptions={{
              classNames: {
                toast:   '!border',
                success: '!border-emerald-500/40',
                error:   '!border-red-500/40',
              },
              style: {
                background: 'var(--surface-elevated)',
                border:     '1px solid var(--border)',
                color:      'var(--fg)',
              },
            }}
          />
        </Providers>
      </body>
    </html>
  )
}
