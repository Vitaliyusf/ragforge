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
  if (loading) {
    return <div className="min-h-screen bg-bg-primary" aria-label="Loading session" />
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
