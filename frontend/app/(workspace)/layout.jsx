/**
 * Persistent workspace shell for `/` and `/chat/[chatId]`.
 *
 * The shell lives here rather than in the pages on purpose. Selecting a chat
 * calls router.push('/chat/<id>'), and in the App Router a *page* remounts on
 * every navigation while a *layout* persists. With TabbedPageLayout in the
 * pages, each chat click tore down and rebuilt Header and the active tab —
 * visible as a full page flash and three redundant requests per click
 * (model-management/implementations, config, files/suggested-questions).
 *
 * The route group keeps both URLs unchanged. The pages beneath render nothing:
 * ChatContext already derives the current chat from usePathname, so the URL
 * alone drives which conversation is shown.
 */
'use client'

import TabbedPageLayout from '@/components/layout/TabbedPageLayout'

export default function WorkspaceLayout({ children }) {
  return (
    <>
      <TabbedPageLayout defaultTab="chat" />
      {children}
    </>
  )
}
