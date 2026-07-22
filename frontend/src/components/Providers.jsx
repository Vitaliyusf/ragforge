/** Redux + Theme + Chat providers */
'use client'

import { useEffect } from 'react'
import { Provider, useDispatch } from 'react-redux'
import { ThemeProvider } from 'next-themes'
import { store } from '@/store'
import { ChatProvider } from '@/features/chat'
import { AuthProvider, LoginForm, useAuth } from '@/features/auth'
import fileService from '@/features/files/services/fileService'
import { setFiles } from '@/store/slices/filesSlice'

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
