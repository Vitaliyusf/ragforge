'use client'

import { createContext, useContext } from 'react'

/**
 * The shell's own navigation, made reachable from anywhere inside it.
 *
 * Cross-screen deep links start deep in a feature — a row in a metrics table,
 * an id in the chat inspector — and threading `onNavigate` down to each of
 * them would have put a navigation prop on components that otherwise know
 * nothing about the shell. This exposes the *same* `setActiveTab` the shell
 * already owns; it is not a second navigation state.
 *
 * The optional `intent` is how a destination learns why it was opened. Only
 * destinations whose filter state is local need one: anything already held in
 * Redux (the log viewer's filters) is set before the jump instead.
 */
const NavigationContext = createContext(null)

const NOOP_NAVIGATION = Object.freeze({ navigate: () => {}, followDeepLink: () => {} })

export function NavigationProvider({ value, children }) {
  return <NavigationContext.Provider value={value}>{children}</NavigationContext.Provider>
}

/**
 * @returns {{navigate: (destination: string, intent?: object) => void,
 *   followDeepLink: (link: ?object) => void}} the shell's navigation, or an
 *   inert one when rendered outside the shell — a panel under test must
 *   render, not throw.
 */
export function useWorkspaceNavigation() {
  return useContext(NavigationContext) ?? NOOP_NAVIGATION
}
