/** Calm workspace header: pillared navigation and one global activity control. */
'use client'

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { Cpu, Sun, Moon, ChevronDown, Layers, LogOut } from 'lucide-react'
import { configService } from '@/features/config'
import { useTheme } from '@/context/ThemeContext'
import { config as appConfig } from '@/lib/config'
import { cn } from '@/lib/utils'
import { useAuth } from '@/features/auth'
import {
  ACTIVITY_FEATURES,
  ACTIVITY_STATES,
  ActivityDot,
  GlobalActivityControl,
  NavActivityIndicator,
  describeActivity,
  summarizeActivity,
  useActivity,
} from '@/features/activity'
import { useI18n } from '@/i18n'
import LanguageSwitcher from './LanguageSwitcher'
import { navigationForRole } from './navigationModel'

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

/** One navigation item, with the activity its feature published on it. */
function NavItem({ destination, active, activity, onSelect }) {
  const { t } = useI18n()
  const { id, labelKey, icon: Icon } = destination
  const label = t(labelKey)
  // Background work is announced on the item itself: the status has to
  // survive a tooltip nobody hovers and a screen reader that never sees one.
  const activityState = activity?.state || ACTIVITY_STATES.IDLE
  const activityText =
    activityState === ACTIVITY_STATES.IDLE ? null : describeActivity(id, activity, t)
  const working =
    activityState === ACTIVITY_STATES.RUNNING || activityState === ACTIVITY_STATES.QUEUED

  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      aria-label={activityText || label}
      title={activityText || undefined}
      data-activity-state={activityState === ACTIVITY_STATES.IDLE ? undefined : activityState}
      data-destination={id}
      aria-current={active ? 'page' : undefined}
      className={cn(
        'relative flex h-9 shrink-0 items-center justify-center gap-2 rounded-lg px-3 text-[13px] font-medium',
        'transition-colors duration-150 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
        active ? 'text-[var(--fg)]' : 'text-[var(--fg-soft)] hover:text-[var(--fg)]'
      )}
    >
      {/* Was a framer-motion shared-element pill. A per-button background
          cross-fades instead: no slide, but it keeps framer-motion out of the
          first-load bundle. */}
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
          color: active ? 'var(--primary)' : working ? 'var(--accent)' : undefined,
        }}
      />
      {/* 1600px, not a named step. The ten labelled destinations measure
          ~1006px, and the nav only gets what the brand and the right-hand
          cluster leave it: 955px at 1366 and 1000px at 1536. Revealing labels
          at xl therefore clipped the first and last destination behind a
          scrollbar-none horizontal scroller with no affordance, and 2xl only
          moved the same clipping to 1536 — that is the breakpoint where the
          runtime pill and user chip expand too, so supply drops exactly where
          demand rises. 1600 is the first width that fits both. The button
          keeps its aria-label, so the icon-only state below is still announced
          in full. */}
      <span className="relative z-10 hidden min-[1600px]:inline">{label}</span>
      {activity && <NavActivityIndicator state={activityState} selected={active} />}
      {activityText && (
        <span className="sr-only" role="status">
          {activityText}
        </span>
      )}
    </button>
  )
}

export default function Header({ activeTab, setActiveTab }) {
  const { resolvedTheme, toggleTheme } = useTheme()
  const { t } = useI18n()
  const { activities } = useActivity()
  const { user, isAdmin, logout } = useAuth()
  const [showRuntime, setShowRuntime] = useState(false)
  const [currentImplementation, setCurrentImplementation] = useState(null)
  const isOnline = useSyncExternalStore(
    subscribeToOnline,
    getOnlineSnapshot,
    getOnlineServerSnapshot
  )
  const runtimeRef = useRef(null)

  // The header renders what the role may see; the shell resolves what it may
  // open from the same model, so the two cannot disagree.
  const role = user?.role || (isAdmin ? 'admin' : 'user')
  const navigationGroups = useMemo(
    () => navigationForRole(role, { features: { training: appConfig.enableTrainingTab } }),
    [role]
  )

  const summary = useMemo(
    () => summarizeActivity(activities, { online: isOnline }),
    [activities, isOnline]
  )

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
    if (!showRuntime) return undefined

    const outsideHandler = (event) => {
      if (runtimeRef.current && !runtimeRef.current.contains(event.target)) {
        setShowRuntime(false)
      }
    }
    const keyHandler = (event) => {
      if (event.key === 'Escape') setShowRuntime(false)
    }
    document.addEventListener('mousedown', outsideHandler)
    document.addEventListener('keydown', keyHandler)
    return () => {
      document.removeEventListener('mousedown', outsideHandler)
      document.removeEventListener('keydown', keyHandler)
    }
  }, [showRuntime])

  return (
    <header className="relative z-50 shrink-0 px-3 pt-3">
      <div
        className="glass-panel flex h-16 items-center rounded-2xl border px-3 shadow-sm md:px-4"
        style={{ borderColor: 'var(--border)' }}
      >
        <button
          type="button"
          onClick={() => setActiveTab('chat')}
          className="group flex shrink-0 items-center gap-2.5 rounded-xl pe-1 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
          aria-label={t('brand.goToChat')}
        >
          <span className="relative flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-primary">
            <Layers size={19} className="text-white" strokeWidth={2} />
            <ActivityDot summary={summary} />
          </span>
          {/* The wordmark is a proper noun and stays LTR in every locale; the
              tagline beneath it is copy and follows the interface direction. */}
          <span className="hidden text-start lg:block">
            <span
              dir="ltr"
              className="block text-[15px] font-semibold leading-5 tracking-[-0.01em] text-[var(--fg)] [unicode-bidi:isolate]"
            >
              RAG<span className="text-[var(--primary)]">Forge</span>
            </span>
            <span className="block text-xs leading-4 text-[var(--fg-soft)]">
              {t('brand.tagline')}
            </span>
          </span>
        </button>

        {/* Pillars, not a flat list of subsystems. Each group is a labelled
            landmark for assistive technology and a hairline rule for everyone
            else, so Chat and Logs stop reading as peers. */}
        <nav
          className="mx-2 flex min-w-0 flex-1 justify-center overflow-x-auto scrollbar-none md:mx-4"
          aria-label={t('nav.main')}
        >
          <div
            className="flex items-center gap-0.5 rounded-xl border p-1"
            style={{ background: 'var(--surface-hover)', borderColor: 'var(--border)' }}
          >
            {navigationGroups.map((group, index) => (
              <div key={group.pillar} className="flex items-center gap-0.5">
                {index > 0 && (
                  <span
                    aria-hidden="true"
                    className="nav-pillar-divider"
                    style={{ background: 'var(--border)' }}
                  />
                )}
                <div
                  role="group"
                  aria-label={t(group.labelKey)}
                  data-pillar={group.pillar}
                  className="flex items-center gap-0.5"
                >
                  {group.items.map((destination) => (
                    <NavItem
                      key={destination.id}
                      destination={destination}
                      active={activeTab === destination.id}
                      activity={
                        ACTIVITY_TABS.has(destination.id) ? activities[destination.id] : null
                      }
                      onSelect={setActiveTab}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </nav>

        <div className="flex shrink-0 items-center gap-0.5">
          <GlobalActivityControl summary={summary} />

          {/* Language sits beside the theme toggle: both are "how this
              workspace is presented to me", and neither touches the other's
              stored preference. */}
          <LanguageSwitcher buttonClassName={iconButtonClass} />

          <button
            type="button"
            onClick={toggleTheme}
            aria-label={resolvedTheme === 'dark' ? t('theme.switchToLight') : t('theme.switchToDark')}
            title={resolvedTheme === 'dark' ? t('theme.light') : t('theme.dark')}
            className={iconButtonClass}
          >
            <span key={resolvedTheme} className="flex animate-icon-swap">
              {resolvedTheme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </span>
          </button>

          {/* Runtime, not Settings: Settings is a destination in the
              Administration pillar now, and two controls called Settings that
              did different jobs was exactly the duplication this replaces.
              What stays here is read-only deployment fact. */}
          {isAdmin && (
            <div ref={runtimeRef} className="relative">
              <button
                type="button"
                onClick={() => setShowRuntime((value) => !value)}
                aria-label={t('runtime.details')}
                aria-expanded={showRuntime}
                className={cn(
                  'flex h-9 items-center gap-1.5 rounded-xl px-2 text-[13px] font-medium transition-colors duration-150',
                  'focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
                  showRuntime
                    ? 'bg-[var(--primary-soft)] text-[var(--primary)]'
                    : 'text-[var(--fg-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--fg)]'
                )}
              >
                <Cpu size={16} />
                {/* An implementation name is a technical identifier and must
                    not be reordered by the surrounding RTL run. */}
                <span className="hidden 2xl:inline">
                  {currentImplementation
                    ? <span dir="ltr" className="[unicode-bidi:isolate]">{currentImplementation}</span>
                    : t('runtime.title')}
                </span>
                <ChevronDown
                  size={12}
                  className={cn(
                    'hidden transition-transform duration-200 sm:block',
                    showRuntime && 'rotate-180'
                  )}
                />
              </button>

              {showRuntime && (
                <div
                  className="animate-dropdown-in absolute end-0 top-full z-[1000] mt-2 w-[min(19rem,calc(100vw-1.5rem))] overflow-hidden rounded-2xl border"
                  style={{
                    background: 'var(--surface-elevated)',
                    borderColor: 'var(--border)',
                    boxShadow: 'var(--shadow-xl)',
                  }}
                >
                  <div className="border-b px-4 py-3" style={{ borderColor: 'var(--border)' }}>
                    <p className="text-[15px] font-semibold text-[var(--fg)]">{t('runtime.title')}</p>
                    <p className="mt-0.5 text-xs text-[var(--fg-soft)]">
                      {t('runtime.deploymentOwned')}
                    </p>
                  </div>

                  <div className="p-3">
                    <p className="label-xs mb-2 px-1">{t('runtime.effectiveImplementation')}</p>
                    <div
                      dir={currentImplementation ? 'ltr' : undefined}
                      className="rounded-xl border border-[var(--border-focus)] bg-[var(--primary-soft)] px-3 py-2.5 text-[13px] font-medium text-[var(--primary)] text-start"
                    >
                      {currentImplementation || t('common.unavailable')}
                    </div>
                    <p className="mt-2 px-1 text-xs text-[var(--fg-soft)]">
                      {t('runtime.restartNote')}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}

          <span
            className="hidden max-w-32 truncate px-2 text-xs text-[var(--fg-soft)] 2xl:block"
            title={user?.email}
          >
            {user?.display_name || user?.email}
          </span>
          <button
            type="button"
            onClick={logout}
            aria-label={t('session.signOut')}
            title={t('session.signOut')}
            className={iconButtonClass}
          >
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </header>
  )
}
