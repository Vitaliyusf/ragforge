/** Redux + Theme + Chat providers */
'use client'

import { useEffect } from 'react'
import dynamic from 'next/dynamic'
import { Provider, useDispatch } from 'react-redux'
import { ThemeProvider } from 'next-themes'
import { store } from '@/store'
import { AuthProvider, LoginForm, useAuth } from '@/features/auth'
import fileService from '@/features/files/services/fileService'
import { setFiles } from '@/store/slices/filesSlice'

// Deliberately NOT `from '@/features/chat'`: that barrel also exports ChatTab,
// which reaches TraceDebugPanel and react-markdown — pulling the whole chat
// feature into the first load and defeating TabbedPageLayout's dynamic import
// of ChatTab. Loading it dynamically also keeps it out of the pre-login bundle,
// since nothing below the auth gate renders until a session exists.
const ChatProvider = dynamic(
  () => import('@/features/chat/context/ChatContext').then((m) => m.ChatProvider),
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
  const { isAuthenticated, loading } = useAuth()
  if (loading) {
    return <div className="min-h-screen bg-bg-primary" aria-label="Loading session" />
  }
  if (!isAuthenticated) return <LoginForm />
  return (
    <ChatProvider>
      <FilePrefetcher />
      {children}
    </ChatProvider>
  )
}

export function Providers({ children }) {
  return (
    <Provider store={store}>
      <ThemeProvider
        attribute="class"
        defaultTheme="dark"
        enableSystem
        disableTransitionOnChange={false}
      >
        <AuthProvider>
          <AuthenticatedApplication>{children}</AuthenticatedApplication>
        </AuthProvider>
      </ThemeProvider>
    </Provider>
  )
}
