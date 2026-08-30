'use client'

/**
 * App shell — renders the sticky header and the active tab content.
 * Each tab controls its own padding and layout.
 */

import { Activity, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import { useDispatch } from 'react-redux'
import Header from '@/components/layout/Header'
import TabSkeleton from '@/components/ui/TabSkeleton'
import ErrorBoundary from '@/components/ErrorBoundary'
import { config as appConfig } from '@/lib/config'
import { useAuth } from '@/features/auth'
import { ACTIVITY_FEATURES, isTerminalState, useActivity } from '@/features/activity'
import { FALLBACK_TAB, allowedTabsForRole } from './navigationModel'
import { NavigationProvider } from './NavigationContext'
import { createDeepLinkFollower } from '@/lib/observability/followDeepLink'
import {
  setSelectedServices,
  setSeverityFilter,
  setTextFilter,
} from '@/store/slices/logsSlice'

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
 * Tabs kept alive across navigation with React's <Activity>.
 *
 * The list is deliberately short. A hidden Activity keeps its subtree's state
 * and DOM in memory, so it is only worth it where mount/unmount destroys work
 * the operator did by hand:
 *
 *   chat    — composer draft and message scroll position
 *   files   — search text, status filter, open audit drawer, table scroll
 *   metrics — selected section, time window and tenant
 *   eval    — in-progress setup form and importer state
 *
 * Everything else (logs, health, models, config, memory, users, upload,
 * training) rebuilds its view from Redux or from its own fetch on mount, so
 * retaining it would buy memory cost and nothing else.
 *
 * A hidden subtree has its Effects torn down exactly as an unmount would, so
 * polling stops while a tab is off-screen and no subscription is duplicated
 * when it comes back.
 */
const STATE_PRESERVING_TABS = new Set(['chat', 'files', 'metrics', 'eval'])

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

/**
 * @param {string} defaultTab - destination when the route has no opinion.
 * @param {?string} routeTab - destination named by the current URL, if any.
 *   The shell owns tab state; this only re-points it when the route itself
 *   moves to a URL that names a different destination.
 */
export default function TabbedPageLayout({ defaultTab = 'chat', routeTab = null }) {
  const { user, isAdmin } = useAuth()
  const dispatch = useDispatch()
  const router = useRouter()
  const { activities, acknowledge } = useActivity()
  const initialTab = resolveTab(routeTab || defaultTab)
  const [activeTab, setActiveTab] = useState(initialTab)
  const [retainedTabs, setRetainedTabs] = useState(() =>
    STATE_PRESERVING_TABS.has(initialTab) ? [initialTab] : []
  )
  // Why the destination was opened, when a deep link had a reason. Held here
  // rather than in each feature because a retained tab is already mounted
  // when the jump happens and would otherwise never see it.
  const [intent, setIntent] = useState(null)
  // What may be opened comes from the same navigation model the header
  // renders from, so a destination cannot be listed but unreachable — or,
  // worse, unlisted but still openable. It mirrors server authorization; it
  // does not replace it.
  const role = user?.role || (isAdmin ? 'admin' : 'user')
  const allowedTabs = useMemo(
    () => allowedTabsForRole(role, { features: { training: appConfig.enableTrainingTab } }),
    [role]
  )
  const requestedTab = resolveTab(activeTab)
  const safeActiveTab = allowedTabs.has(requestedTab) ? requestedTab : FALLBACK_TAB
  const TabComponent = TAB_COMPONENTS[safeActiveTab]

  // One entry point for every cross-screen jump. `at` gives each jump its own
  // identity, so following the same link twice is two arrivals rather than
  // one the destination silently ignores as an unchanged prop.
  const navigate = useCallback((destination, nextIntent = null) => {
    const resolved = resolveTab(destination)
    setIntent(nextIntent ? { ...nextIntent, destination: resolved, at: Date.now() } : null)
    setActiveTab(resolved)
  }, [])
  // Following a link is the shell's job, not a panel's: only here are the
  // store, the router and the tab state all in reach.
  const followDeepLink = useMemo(
    () => createDeepLinkFollower({
      dispatch,
      router,
      navigate,
      logActions: { setSelectedServices, setSeverityFilter, setTextFilter },
    }),
    [dispatch, router, navigate]
  )
  const navigation = useMemo(() => ({ navigate, followDeepLink }), [navigate, followDeepLink])
  const activeIntent = intent && intent.destination === safeActiveTab ? intent : null

  useEffect(() => {
    if (!allowedTabs.has(resolveTab(activeTab))) setActiveTab(FALLBACK_TAB)
  }, [activeTab, allowedTabs])

  // The URL steers the shell only when the route itself moves to a different
  // named destination. Switching tabs by hand leaves the pathname alone, so
  // this must not fire and drag the operator back to the route's tab.
  const appliedRouteTab = useRef(routeTab)
  useEffect(() => {
    if (!routeTab || routeTab === appliedRouteTab.current) return
    appliedRouteTab.current = routeTab
    setActiveTab(routeTab)
  }, [routeTab])

  // A retained tab is only paid for once it has actually been opened.
  useEffect(() => {
    if (!STATE_PRESERVING_TABS.has(safeActiveTab)) return
    setRetainedTabs((tabs) => (tabs.includes(safeActiveTab) ? tabs : [...tabs, safeActiveTab]))
  }, [safeActiveTab])

  // Opening a feature is the acknowledgement: the page itself now shows the
  // authoritative result, so the nav marker has done its job. Only terminal
  // state clears — work that is still running keeps its indicator.
  const visibleActivityState = activities[safeActiveTab]?.state
  useEffect(() => {
    if (!ACKNOWLEDGEABLE.has(safeActiveTab)) return
    if (isTerminalState(visibleActivityState)) acknowledge(safeActiveTab)
  }, [safeActiveTab, visibleActivityState, acknowledge])

  return (
    <NavigationProvider value={navigation}>
    <div
      className="app-backdrop isolate flex h-[100dvh] flex-col overflow-hidden"
      style={{ color: 'var(--fg)' }}
    >
      <Header activeTab={safeActiveTab} setActiveTab={setActiveTab} />

      <main
        id="main-content"
        className="relative z-10 flex min-h-0 flex-1 flex-col overflow-hidden"
      >
        {/* Retained workspaces stay mounted and merely hide, which is what
            preserves their local state. Their enter animation therefore plays
            on first open only — a returning tab is meant to look exactly as it
            was left. */}
        {retainedTabs.map((id) => {
          const RetainedTab = TAB_COMPONENTS[id]
          if (!RetainedTab) return null
          return (
            <Activity key={id} mode={id === safeActiveTab ? 'visible' : 'hidden'}>
              <div className="flex min-h-0 flex-1 animate-fade-in flex-col overflow-hidden">
                <ErrorBoundary name={id}>
                  <RetainedTab
                    onNavigate={setActiveTab}
                    intent={id === safeActiveTab ? activeIntent : null}
                  />
                </ErrorBoundary>
              </div>
            </Activity>
          )
        })}

        {/* Every other tab is still keyed so React remounts it on entry, which
            restarts the CSS enter animation. Previously framer-motion —
            dropping it here (and in Header and Modal) keeps the library out of
            the first load. */}
        {!STATE_PRESERVING_TABS.has(safeActiveTab) && (
          TabComponent ? (
            <div
              key={safeActiveTab}
              className="flex min-h-0 flex-1 animate-fade-in flex-col overflow-hidden"
            >
              <ErrorBoundary name={safeActiveTab}>
                <TabComponent onNavigate={setActiveTab} intent={activeIntent} />
              </ErrorBoundary>
            </div>
          ) : (
            <div key="skeleton" className="flex min-h-0 flex-1 animate-fade-in flex-col">
              <TabSkeleton />
            </div>
          )
        )}
      </main>
    </div>
    </NavigationProvider>
  )
}
