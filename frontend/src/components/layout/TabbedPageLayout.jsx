'use client'

/**
 * App shell — renders the sticky header and the active tab content.
 * Each tab controls its own padding and layout.
 */

import { useEffect, useState } from 'react'
import dynamic from 'next/dynamic'
import Header from '@/components/layout/Header'
import TabSkeleton from '@/components/ui/TabSkeleton'
import ErrorBoundary from '@/components/ErrorBoundary'
import { config as appConfig } from '@/lib/config'
import { useAuth } from '@/features/auth'
import { ACTIVITY_FEATURES, isTerminalState, useActivity } from '@/features/activity'

const ChatTab = dynamic(() => import('@/features/chat/components/ChatTab'), {
  loading: () => <TabSkeleton />, ssr: false,
})
const FilesTab = dynamic(() => import('@/features/files/components/FilesTab'), {
  loading: () => <TabSkeleton />, ssr: false,
})
const LogsTab = dynamic(() => import('@/features/logs/components/LogsTab'), {
  loading: () => <TabSkeleton />, ssr: false,
})
const ModelManagementTab = dynamic(
  () => import('@/features/models/components/ModelManagementTab'),
  { loading: () => <TabSkeleton />, ssr: false }
)
const ConfigTab = dynamic(() => import('@/features/config/components/ConfigTab'), {
  loading: () => <TabSkeleton />, ssr: false,
})
const LongTermMemoryTab = dynamic(
  () => import('@/features/memory/components/LongTermMemoryTab'),
  { loading: () => <TabSkeleton />, ssr: false }
)
const HealthDashboard = dynamic(
  () => import('@/features/health/components/HealthDashboard'),
  { loading: () => <TabSkeleton />, ssr: false }
)
const MetricsTab = dynamic(
  () => import('@/features/metrics/components/MetricsTab'),
  { loading: () => <TabSkeleton />, ssr: false }
)
const EvalTab = dynamic(
  () => import('@/features/eval/components/EvalTab'),
  { loading: () => <TabSkeleton />, ssr: false }
)
const TrainingTab = dynamic(() => import('@/features/training/components/TrainingTab'), {
  loading: () => <TabSkeleton />, ssr: false,
})
const AdminUsersTab = dynamic(() => import('@/features/admin/components/AdminUsersTab'), {
  loading: () => <TabSkeleton />, ssr: false,
})
const UploadTab = dynamic(() => import('@/features/files/components/UploadTab'), {
  loading: () => <TabSkeleton />, ssr: false,
})

const TAB_COMPONENTS = {
  chat:     ChatTab,
  files:    FilesTab,
  logs:     LogsTab,
  models:   ModelManagementTab,
  config:   ConfigTab,
  memory:   LongTermMemoryTab,
  health:   HealthDashboard,
  metrics:  MetricsTab,
  eval:     EvalTab,
  users:    AdminUsersTab,
  upload:   UploadTab,
  ...(appConfig.enableTrainingTab ? { training: TrainingTab } : {}),
}

/**
 * Destinations that used to live inside another tab.
 *
 * Eval was a Metrics sub-section before it became a workspace of its own.
 * Anything still pointing at it by the old name resolves to the new
 * top-level destination rather than falling through to Chat, which would
 * look like the feature had been removed.
 */
export const LEGACY_TAB_ALIASES = {
  'metrics/eval': 'eval',
  'metrics:eval': 'eval',
  'metrics-eval': 'eval',
}

export function resolveTab(tab) {
  return LEGACY_TAB_ALIASES[tab] || tab
}

const ACKNOWLEDGEABLE = new Set(Object.values(ACTIVITY_FEATURES))

export default function TabbedPageLayout({ defaultTab = 'chat' }) {
  const { isAdmin } = useAuth()
  const { activities, acknowledge } = useActivity()
  const [activeTab, setActiveTab] = useState(resolveTab(defaultTab))
  const allowedTabs = isAdmin
    ? new Set(['chat', 'files', 'logs', 'models', 'config', 'memory', 'health', 'metrics', 'eval', 'users', ...(appConfig.enableTrainingTab ? ['training'] : [])])
    : new Set(['chat', 'upload', 'memory'])
  const requestedTab = resolveTab(activeTab)
  const safeActiveTab = allowedTabs.has(requestedTab) ? requestedTab : 'chat'
  const TabComponent = TAB_COMPONENTS[safeActiveTab]

  useEffect(() => {
    if (!allowedTabs.has(resolveTab(activeTab))) setActiveTab('chat')
  }, [activeTab, isAdmin])

  // Opening a feature is the acknowledgement: the page itself now shows the
  // authoritative result, so the nav marker has done its job. Only terminal
  // state clears — work that is still running keeps its indicator.
  const visibleActivityState = activities[safeActiveTab]?.state
  useEffect(() => {
    if (!ACKNOWLEDGEABLE.has(safeActiveTab)) return
    if (isTerminalState(visibleActivityState)) acknowledge(safeActiveTab)
  }, [safeActiveTab, visibleActivityState, acknowledge])

  return (
    <div
      className="app-backdrop isolate flex h-[100dvh] flex-col overflow-hidden"
      style={{ color: 'var(--fg)' }}
    >
      <Header activeTab={safeActiveTab} setActiveTab={setActiveTab} />

      <main
        id="main-content"
        className="relative z-10 flex min-h-0 flex-1 flex-col overflow-hidden"
      >
        {/* Keyed so React remounts on tab change, which restarts the CSS
            enter animation. Previously framer-motion — dropping it here (and
            in Header and Modal) keeps the library out of the first load. */}
        {TabComponent ? (
          <div
            key={safeActiveTab}
            className="flex min-h-0 flex-1 animate-fade-in flex-col overflow-hidden"
          >
            <ErrorBoundary name={safeActiveTab}>
              <TabComponent onNavigate={setActiveTab} />
            </ErrorBoundary>
          </div>
        ) : (
          <div key="skeleton" className="flex min-h-0 flex-1 animate-fade-in flex-col">
            <TabSkeleton />
          </div>
        )}
      </main>
    </div>
  )
}
