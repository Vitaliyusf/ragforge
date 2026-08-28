/**
 * Route → workspace destination mapping.
 *
 * The shell keeps its own tab state (PRODUCT-01 owns whether that eventually
 * becomes URL-driven). This map exists so the routes that *do* name a
 * destination — `/settings` — open it inside the persistent shell instead of
 * rendering a second, shell-less copy of the feature.
 *
 * A pathname with no opinion returns null, which leaves the current tab alone.
 */
export function tabForPathname(pathname) {
  if (!pathname) return null
  if (pathname === '/settings') return 'config'
  if (pathname === '/' || pathname === '/dashboard') return 'chat'
  if (pathname.startsWith('/chat/')) return 'chat'
  return null
}
