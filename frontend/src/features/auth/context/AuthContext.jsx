'use client'

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import authService from '@/features/auth/services/authService'
import { store } from '@/store'

const AuthContext = createContext(null)

function clearBrowserState() {
  store.dispatch({ type: 'auth/sessionChanged' })
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem('persist:logs')
    window.localStorage.removeItem('persist:files')
    window.localStorage.removeItem('logs')
    window.localStorage.removeItem('files')
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    authService.getCurrentUser()
      .then((response) => {
        if (active) setUser(response?.user || null)
      })
      .catch(() => {
        if (active) setUser(null)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => { active = false }
  }, [])

  const login = useCallback(async (tenant, email, password) => {
    setLoading(true)
    setError(null)
    try {
      clearBrowserState()
      const response = await authService.login(tenant, email, password)
      setUser(response.user)
      return response
    } catch (loginError) {
      setError(loginError?.message || 'Login failed')
      throw loginError
    } finally {
      setLoading(false)
    }
  }, [])

  const setup = useCallback(async (email, displayName, password) => {
    setLoading(true)
    setError(null)
    try {
      clearBrowserState()
      const response = await authService.setup(email, displayName, password)
      setUser(response.user)
      return response
    } catch (setupError) {
      setError(setupError?.message || 'Setup failed')
      throw setupError
    } finally {
      setLoading(false)
    }
  }, [])

  const logout = useCallback(async () => {
    setLoading(true)
    try {
      await authService.logout()
    } finally {
      // Imported here rather than at module scope: AuthProvider mounts before
      // login, and a static import puts socket.io-client in the first load for
      // visitors who only ever see the login screen.
      const { default: socketService } = await import('@/features/websocket/services/socketService')
      socketService.disconnect()
      clearBrowserState()
      setUser(null)
      setLoading(false)
    }
  }, [])

  const value = useMemo(() => ({
    user,
    loading,
    error,
    isAuthenticated: Boolean(user),
    isAdmin: user?.role === 'admin',
    login,
    setup,
    logout,
  }), [user, loading, error, login, setup, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuthContext() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
