/**
 * Backward-compat shim — wraps next-themes so existing code that
 * imports from '@/context/ThemeContext' keeps working unchanged.
 * next-themes ThemeProvider is mounted in Providers.jsx.
 */
'use client'

import { useTheme as useNextTheme } from 'next-themes'

/** Drop-in replacement for the old useTheme() hook. */
export function useTheme() {
  const { theme, setTheme, resolvedTheme } = useNextTheme()

  const toggleTheme = () => {
    setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')
  }

  return { theme, resolvedTheme: resolvedTheme ?? 'dark', setTheme, toggleTheme }
}
