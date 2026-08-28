/** Calm workspace header with focused primary navigation. */
'use client'

import { useEffect, useRef, useState, useSyncExternalStore } from 'react'
import {
  MessageSquare,
  Files,
  FlaskConical,
  Terminal,
  Cpu,
  Zap,
  HeartPulse,
  BarChart3,
  Settings2,
  Brain,
  Sun,
  Moon,
  WifiOff,
  ChevronDown,
  Layers,
  Users,
  Upload,
  LogOut,
} from 'lucide-react'
import { configService } from '@/features/config'
import { useTheme } from '@/context/ThemeContext'
import { config as appConfig } from '@/lib/config'
import { cn } from '@/lib/utils'
import { useAuth } from '@/features/auth'
import {
  ACTIVITY_FEATURES,
  ACTIVITY_STATES,
  NavActivityIndicator,
  describeActivity,
  useActivity,
} from '@/features/activity'

const ADMIN_TABS = [
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'files', label: 'Files', icon: Files },
  { id: 'eval', label: 'Eval', icon: FlaskConical },
  { id: 'users', label: 'Users', icon: Users },
  { id: 'models', label: 'Models', icon: Cpu },
  { id: 'logs', label: 'Logs', icon: Terminal },
  { id: 'health', label: 'Health', icon: HeartPulse },
  { id: 'metrics', label: 'Metrics', icon: BarChart3 },
  ...(appConfig.enableTrainingTab ? [{ id: 'training', label: 'Training', icon: Zap }] : []),
]

const USER_TABS = [
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'upload', label: 'Upload', icon: Upload },
]

const iconButtonClass = [
  'relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl',
  'text-[var(--fg-muted)] transition-colors duration-150',
  'hover:bg-[var(--surface-hover)] hover:text-[var(--fg)]',
  'focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
].join(' ')

const ACTIVITY_TABS = new Set(Object.values(ACTIVITY_FEATURES))

// Connectivity is external browser state, so React subscribes to it directly
// instead of copying it into component state from an Effect. The server
// snapshot is `true` so SSR and the first client render agree; a genuinely
// offline client corrects itself on the store's first notification.
function subscribeToOnline(onStoreChange) {
  window.addEventListener('online', onStoreChange)
  window.addEventListener('offline', onStoreChange)
  return () => {
    window.removeEventListener('online', onStoreChange)
    window.removeEventListener('offline', onStoreChange)
  }
}

const getOnlineSnapshot = () => navigator.onLine
const getOnlineServerSnapshot = () => true

export default function Header({ activeTab, setActiveTab }) {
  const { resolvedTheme, toggleTheme } = useTheme()
  const { activities } = useActivity()
  const { user, isAdmin, logout } = useAuth()
  const navigationTabs = isAdmin ? ADMIN_TABS : USER_TABS
  const [showSettings, setShowSettings] = useState(false)
  const [currentImplementation, setCurrentImplementation] = useState(null)
  const isOnline = useSyncExternalStore(
    subscribeToOnline,
    getOnlineSnapshot,
    getOnlineServerSnapshot
  )
  const settingsRef = useRef(null)

  useEffect(() => {
    if (!isAdmin) return
    const load = async () => {
      try {
        const configData = await configService.getConfig()
        if (configData?.llm_implementation) {
          setCurrentImplementation(configData.llm_implementation)
        }
      } catch (err) {
        console.error('Header: failed to load settings', err)
      }
    }
    load()
  }, [isAdmin])

  // Dismissal listeners exist only while the menu is open — previously two
  // document-level listeners stayed attached for the whole session to serve a
  // popover that is closed almost all of the time.
  useEffect(() => {
    if (!showSettings) return undefined

    const outsideHandler = (event) => {
      if (settingsRef.current && !settingsRef.current.contains(event.target)) {
        setShowSettings(false)
      }
    }
    const keyHandler = (event) => {
      if (event.key === 'Escape') setShowSettings(false)
    }
    document.addEventListener('mousedown', outsideHandler)
    document.addEventListener('keydown', keyHandler)
    return () => {
      document.removeEventListener('mousedown', outsideHandler)
      document.removeEventListener('keydown', keyHandler)
    }
  }, [showSettings])

  const settingsActive = activeTab === 'config' || activeTab === 'memory'

  return (
    <header className="relative z-50 shrink-0 px-3 pt-3">
      <div
        className="glass-panel flex h-16 items-center rounded-2xl border px-3 shadow-sm md:px-4"
        style={{ borderColor: 'var(--border)' }}
      >
        <button
          type="button"
          onClick={() => setActiveTab('chat')}
          className="group flex shrink-0 items-center gap-2.5 rounded-xl pr-1 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
          aria-label="Go to chat"
        >
          <span className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-primary">
            <Layers size={19} className="text-white" strokeWidth={2} />
            <span
              className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2"
              style={{ background: 'var(--accent)', borderColor: 'var(--surface-elevated)' }}
            />
          </span>
          <span className="hidden text-left lg:block">
            <span className="block text-[15px] font-semibold leading-5 tracking-[-0.01em] text-[var(--fg)]">
              RAG<span className="text-[var(--primary)]">Forge</span>
            </span>
            <span className="block text-xs leading-4 text-[var(--fg-soft)]">AI workspace</span>
          </span>
        </button>

        <nav
          className="mx-2 flex min-w-0 flex-1 justify-center overflow-x-auto scrollbar-none md:mx-4"
          aria-label="Main navigation"
        >
          <div
            className="flex items-center gap-0.5 rounded-xl border p-1"
            style={{ background: 'var(--surface-hover)', borderColor: 'var(--border)' }}
          >
            {navigationTabs.map(({ id, label, icon: Icon }) => {
              const active = activeTab === id
              // Background work is announced on the item itself: the status
              // has to survive a tooltip nobody hovers and a screen reader
              // that never sees one.
              const activity = ACTIVITY_TABS.has(id) ? activities[id] : null
              const activityState = activity?.state || ACTIVITY_STATES.IDLE
              const activityText =
                activityState === ACTIVITY_STATES.IDLE ? null : describeActivity(id, activity)
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setActiveTab(id)}
                  aria-label={activityText || label}
                  title={activityText || undefined}
                  data-activity-state={activityState === ACTIVITY_STATES.IDLE ? undefined : activityState}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'relative flex h-9 shrink-0 items-center justify-center gap-2 rounded-lg px-3 text-[13px] font-medium',
                    'transition-colors duration-150 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
                    active ? 'text-[var(--fg)]' : 'text-[var(--fg-soft)] hover:text-[var(--fg)]'
                  )}
                >
                  {/* Was a framer-motion shared-element pill. A per-button
                      background cross-fades instead: no slide, but it keeps
                      framer-motion out of the first-load bundle. */}
                  <span
                    aria-hidden="true"
                    className="absolute inset-0 rounded-lg border transition-opacity duration-200"
                    style={{
                      background: 'var(--surface-elevated)',
                      borderColor: 'var(--border)',
                      boxShadow: 'var(--shadow-sm)',
                      opacity: active ? 1 : 0,
                    }}
                  />
                  <Icon
                    size={16}
                    strokeWidth={active ? 2.2 : 1.8}
                    className="relative z-10"
                    style={{
                      color: active
                        ? 'var(--primary)'
                        : activityState === ACTIVITY_STATES.RUNNING ||
                            activityState === ACTIVITY_STATES.QUEUED
                          ? 'var(--accent)'
                          : undefined,
                    }}
                  />
                  <span className="relative z-10 hidden xl:inline">{label}</span>
                  {activity && (
                    <NavActivityIndicator state={activityState} selected={active} />
                  )}
                  {activityText && (
                    <span className="sr-only" role="status">
                      {activityText}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </nav>

        <div className="flex shrink-0 items-center gap-0.5">
          {!isOnline && (
            <div
              className="mr-1 flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium"
              style={{ background: 'var(--danger-soft)', color: 'var(--danger)' }}
            >
              <WifiOff size={11} />
              <span className="hidden sm:inline">Offline</span>
            </div>
          )}

          <button
            type="button"
            onClick={() => setActiveTab('memory')}
            aria-label="Long-term memory"
            title="Long-term memory"
            className={cn(iconButtonClass, activeTab === 'memory' && 'bg-[var(--primary-soft)] text-[var(--primary)]')}
          >
            <Brain size={16} />
          </button>

          <button
            type="button"
            onClick={toggleTheme}
            aria-label={resolvedTheme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            title={resolvedTheme === 'dark' ? 'Light mode' : 'Dark mode'}
            className={iconButtonClass}
          >
            <span key={resolvedTheme} className="flex animate-icon-swap">
              {resolvedTheme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </span>
          </button>

          {isAdmin && <div ref={settingsRef} className="relative">
            <button
              type="button"
              onClick={() => setShowSettings((value) => !value)}
              aria-label="Workspace settings"
              aria-expanded={showSettings}
              className={cn(
                'flex h-9 items-center gap-1.5 rounded-xl px-2 text-[13px] font-medium transition-colors duration-150',
                'focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
                showSettings || settingsActive
                  ? 'bg-[var(--primary-soft)] text-[var(--primary)]'
                  : 'text-[var(--fg-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--fg)]'
              )}
            >
              <Settings2 size={16} />
              <span className="hidden 2xl:inline">{currentImplementation || 'Settings'}</span>
              <ChevronDown
                size={12}
                className={cn('hidden transition-transform duration-200 sm:block', showSettings && 'rotate-180')}
              />
            </button>

            {showSettings && (
              <div
                  className="animate-dropdown-in absolute right-0 top-full z-[1000] mt-2 w-[min(19rem,calc(100vw-1.5rem))] overflow-hidden rounded-2xl border"
                  style={{
                    background: 'var(--surface-elevated)',
                    borderColor: 'var(--border)',
                    boxShadow: 'var(--shadow-xl)',
                  }}
                  role="menu"
                >
                  <div className="border-b px-4 py-3" style={{ borderColor: 'var(--border)' }}>
                    <p className="text-[15px] font-semibold text-[var(--fg)]">Workspace settings</p>
                    <p className="mt-0.5 text-xs text-[var(--fg-soft)]">
                      Model runtime and system preferences
                    </p>
                  </div>

                  <div className="p-3">
                    <p className="label-xs mb-2 px-1">Effective LLM implementation</p>
                    <div className="rounded-xl border border-[var(--border-focus)] bg-[var(--primary-soft)] px-3 py-2.5 text-[13px] font-medium text-[var(--primary)]">
                      {currentImplementation || 'Unavailable'}
                    </div>
                    <p className="mt-2 px-1 text-xs text-[var(--fg-soft)]">
                      Deployment-owned; changes require a service restart.
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-2 border-t p-3" style={{ borderColor: 'var(--border)' }}>
                    <button
                      type="button"
                      onClick={() => {
                        setActiveTab('memory')
                        setShowSettings(false)
                      }}
                      role="menuitem"
                      className="flex items-center justify-center gap-2 rounded-xl bg-[var(--surface-hover)] px-3 py-2.5 text-[13px] font-medium text-[var(--fg-muted)] transition-colors hover:text-[var(--fg)]"
                    >
                      <Brain size={13} /> Memory
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setActiveTab('config')
                        setShowSettings(false)
                      }}
                      role="menuitem"
                      className="flex items-center justify-center gap-2 rounded-xl bg-[var(--primary-soft)] px-3 py-2.5 text-[13px] font-medium text-[var(--primary)] transition-colors hover:bg-[var(--accent-soft)]"
                    >
                      <Settings2 size={13} /> All settings
                    </button>
                  </div>
                </div>
              )}
          </div>}

          <span className="hidden max-w-32 truncate px-2 text-xs text-[var(--fg-soft)] 2xl:block" title={user?.email}>
            {user?.display_name || user?.email}
          </span>
          <button
            type="button"
            onClick={logout}
            aria-label="Sign out"
            title="Sign out"
            className={iconButtonClass}
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </header>
  )
}
