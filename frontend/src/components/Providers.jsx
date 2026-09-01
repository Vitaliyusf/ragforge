/** Redux + Theme + Chat providers */
'use client'

import { useEffect } from 'react'
import dynamic from 'next/dynamic'
import { Provider, useDispatch } from 'react-redux'
import { ThemeProvider } from 'next-themes'
import { Toaster } from 'sonner'
import { store } from '@/store'
import { I18nProvider, useI18n } from '@/i18n'
import { AuthProvider, LoginForm, useAuth } from '@/features/auth'
import fileService from '@/features/files/services/fileService'
import { setFiles } from '@/store/slices/filesSlice'
import { ActivityProvider, EvalActivityProvider, FilesActivityBridge } from '@/features/activity'

// Deliberately NOT `from '@/features/chat'`: that barrel also exports ChatTab,
// which reaches the Developer Inspector and react-markdown — pulling the whole chat
// feature into the first load and defeating TabbedPageLayout's dynamic import
// of ChatTab. Loading it dynamically also keeps it out of the pre-login bundle,
// since nothing below the auth gate renders until a session exists.
const ChatProvider = dynamic(
  () => import('@/features/chat/context/ChatContext').then((m) => m.ChatProvider),
  { ssr: false }
)

// Same reason as ChatProvider: the bridge reads the chat runtime, so a static
// import here would pull the chat feature back into the first load.
const ChatActivityBridge = dynamic(
  () => import('@/features/activity/sources/ChatActivityBridge'),
  { ssr: false }
)

/** Prefetch files once on app start so the Files tab never opens empty. */
function FilePrefetcher() {
  const dispatch = useDispatch()
  const { isAdmin } = useAuth()

  useEffect(() => {
    if (!isAdmin) return
    fileService.getFiles()
      .then((data) => {
        if (data?.files) dispatch(setFiles(data.files))
      })
      .catch(() => {/* silently ignore — hook polling will retry */})
  }, [dispatch, isAdmin])

  return null
}

function AuthenticatedApplication({ children }) {
  const { isAuthenticated, loading, isAdmin } = useAuth()
  const { t } = useI18n()
  if (loading) {
    return <div className="min-h-screen bg-bg-primary" aria-label={t('session.loading')} />
  }
  if (!isAuthenticated) return <LoginForm />
  return (
    <ChatProvider>
      {/* Activity lives above the shell: the point of the nav indicators is
          that they survive leaving the feature that produced them. The Eval
          and Files sources are admin-only because their endpoints are. */}
      <ActivityProvider>
        <EvalActivityProvider enabled={isAdmin}>
          <FilePrefetcher />
          <FilesActivityBridge enabled={isAdmin} />
          <ChatActivityBridge />
          {children}
        </EvalActivityProvider>
      </ActivityProvider>
    </ChatProvider>
  )
}

/**
 * Toasts follow the interface locale, not the server's first guess.
 *
 * They are anchored to the logical *end* of the top edge — top-right in
 * English, top-left in Hebrew — because a notification that appears on the
 * side the reader's eye is leaving is a notification they miss.
 */
function LocalizedToaster() {
  const { direction, isRTL } = useI18n()
  return (
    <Toaster
      position={isRTL ? 'top-left' : 'top-right'}
      dir={direction}
      richColors
      closeButton
      toastOptions={{
        classNames: {
          toast:   '!border',
          success: '!border-success',
          error:   '!border-danger',
        },
        style: {
          background: 'var(--surface-elevated)',
          border:     '1px solid var(--border)',
          color:      'var(--fg)',
        },
      }}
    />
  )
}

/**
 * Provider order is load-bearing.
 *
 * I18n sits *above* AuthProvider so the language control works on the sign-in
 * form too — a reader who cannot read the form cannot sign in to reach the
 * setting that would fix it. It sits below ThemeProvider so the two
 * preferences stay independent: switching language never touches the theme,
 * and switching theme never touches the language.
 */
export function Providers({ children, initialLocale }) {
  return (
    <Provider store={store}>
      <ThemeProvider
        attribute="class"
        defaultTheme="dark"
        enableSystem
        disableTransitionOnChange={false}
      >
        <I18nProvider initialLocale={initialLocale}>
          <AuthProvider>
            <AuthenticatedApplication>{children}</AuthenticatedApplication>
          </AuthProvider>
          <LocalizedToaster />
        </I18nProvider>
      </ThemeProvider>
    </Provider>
  )
}
