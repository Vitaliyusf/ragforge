/**
 * Persistent workspace shell for every application URL.
 *
 * The shell lives here rather than in the pages on purpose. Selecting a chat
 * calls router.push('/chat/<id>'), and in the App Router a *page* remounts on
 * every navigation while a *layout* persists. With TabbedPageLayout in the
 * pages, each chat click tore down and rebuilt Header and the active tab —
 * visible as a full page flash and three redundant requests per click
 * (model-management/implementations, config, files/suggested-questions).
 *
 * `/dashboard` and `/settings` used to sit outside this group and mount their
 * own chrome (a second TabbedPageLayout, and a bare ConfigTab with no header
 * at all). They are now pages in this group too, so the shell survives every
 * transition; the route only names which destination to open.
 *
 * The route group keeps all URLs unchanged. The pages beneath render nothing:
 * ChatContext already derives the current chat from usePathname, so the URL
 * alone drives which conversation is shown.
 */
'use client'

import { usePathname } from 'next/navigation'
import TabbedPageLayout from '@/components/layout/TabbedPageLayout'
import { tabForPathname } from '@/components/layout/routeTabs'

export default function WorkspaceLayout({ children }) {
  const pathname = usePathname()

  return (
    <>
      <TabbedPageLayout defaultTab="chat" routeTab={tabForPathname(pathname)} />
      {children}
    </>
  )
}
