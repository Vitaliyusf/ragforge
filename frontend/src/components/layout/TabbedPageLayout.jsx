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
  users:    AdminUsersTab,
  upload:   UploadTab,
  ...(appConfig.enableTrainingTab ? { training: TrainingTab } : {}),
}

export default function TabbedPageLayout({ defaultTab = 'chat' }) {
  const { isAdmin } = useAuth()
  const [activeTab, setActiveTab] = useState(defaultTab)
  const allowedTabs = isAdmin
    ? new Set(['chat', 'files', 'logs', 'models', 'config', 'memory', 'health', 'metrics', 'users', ...(appConfig.enableTrainingTab ? ['training'] : [])])
    : new Set(['chat', 'upload', 'memory'])
  const safeActiveTab = allowedTabs.has(activeTab) ? activeTab : 'chat'
  const TabComponent = TAB_COMPONENTS[safeActiveTab]

  useEffect(() => {
    if (!allowedTabs.has(activeTab)) setActiveTab('chat')
  }, [activeTab, isAdmin])

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
              <TabComponent />
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
