/** Calm workspace header with focused primary navigation. */
'use client'

import { useEffect, useRef, useState } from 'react'
import {
  MessageSquare,
  Files,
  Terminal,
  Cpu,
  Zap,
  HeartPulse,
  Settings2,
  Brain,
  Sun,
  Moon,
  Check,
  WifiOff,
  ChevronDown,
  Layers,
  Users,
  Upload,
  LogOut,
} from 'lucide-react'
import { AnimatePresence, motion } from 'framer-motion'
import { toast } from 'sonner'
import { configService } from '@/features/config'
import { modelService } from '@/features/models'
import { useTheme } from '@/context/ThemeContext'
import { config as appConfig } from '@/lib/config'
import { cn } from '@/lib/utils'
import { useAuth } from '@/features/auth'

const ADMIN_TABS = [
  { id: 'chat', label: 'Chat', icon: MessageSquare },
  { id: 'files', label: 'Files', icon: Files },
  { id: 'users', label: 'Users', icon: Users },
  { id: 'models', label: 'Models', icon: Cpu },
  { id: 'logs', label: 'Logs', icon: Terminal },
  { id: 'health', label: 'Health', icon: HeartPulse },
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
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
].join(' ')

export default function Header({ activeTab, setActiveTab }) {
  const { resolvedTheme, toggleTheme } = useTheme()
  const { user, isAdmin, logout } = useAuth()
  const navigationTabs = isAdmin ? ADMIN_TABS : USER_TABS
  const [showSettings, setShowSettings] = useState(false)
  const [implementations, setImplementations] = useState([])
  const [currentImplementation, setCurrentImplementation] = useState(null)
  const [loading, setLoading] = useState(false)
  const [isOnline, setIsOnline] = useState(
    typeof navigator !== 'undefined' ? navigator.onLine : true
  )
  const settingsRef = useRef(null)

  useEffect(() => {
    if (!isAdmin) return
    const load = async () => {
      try {
        const [implData, configData] = await Promise.all([
          modelService.getImplementations(),
          configService.getConfig(),
        ])
        const impls = implData?.implementations || implData?.data?.implementations || []
        setImplementations(impls)
        if (configData?.llm_implementation) {
          setCurrentImplementation(configData.llm_implementation)
        }
      } catch (err) {
        console.error('Header: failed to load settings', err)
      }
    }
    load()
  }, [isAdmin])

  useEffect(() => {
    const on = () => setIsOnline(true)
    const off = () => setIsOnline(false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  }, [])

  useEffect(() => {
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
  }, [])

  const handleSwitchImplementation = async (name) => {
    try {
      setLoading(true)
      await configService.switchImplementation(name)
      const cfg = await configService.getConfig()
      if (cfg?.llm_implementation) setCurrentImplementation(cfg.llm_implementation)
      setShowSettings(false)
      toast.success(`Switched to ${name}`)
    } catch (err) {
      toast.error('Failed to switch', { description: err.message })
    } finally {
      setLoading(false)
    }
  }

  const settingsActive = activeTab === 'config' || activeTab === 'memory'

  return (
    <header className="relative z-50 shrink-0 px-3 pt-3">
      <div
        className="glass-panel flex h-14 items-center rounded-2xl border px-2.5 shadow-sm md:px-3"
        style={{ borderColor: 'var(--border)' }}
      >
        <button
          type="button"
          onClick={() => setActiveTab('chat')}
          className="group flex shrink-0 items-center gap-2.5 rounded-xl pr-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]"
          aria-label="Go to chat"
        >
          <span className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-primary shadow-glow">
            <Layers size={16} className="text-white" strokeWidth={2} />
            <span
              className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2"
              style={{ background: 'var(--accent)', borderColor: 'var(--surface-elevated)' }}
            />
          </span>
          <span className="hidden text-left lg:block">
            <span className="block text-sm font-semibold leading-4 tracking-tight text-[var(--fg)]">
              RAG<span className="text-[var(--primary)]">Forge</span>
            </span>
            <span className="block text-[10px] leading-3 text-[var(--fg-soft)]">AI workspace</span>
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
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => setActiveTab(id)}
                  aria-label={label}
                  aria-current={active ? 'page' : undefined}
                  className={cn(
                    'relative flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-lg px-2.5 text-xs font-medium',
                    'transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
                    active ? 'text-[var(--fg)]' : 'text-[var(--fg-soft)] hover:text-[var(--fg)]'
                  )}
                >
                  {active && (
                    <motion.span
                      layoutId="primary-navigation"
                      className="absolute inset-0 rounded-lg border"
                      style={{
                        background: 'var(--surface-elevated)',
                        borderColor: 'var(--border)',
                        boxShadow: 'var(--shadow-sm)',
                      }}
                      transition={{ type: 'spring', damping: 30, stiffness: 420 }}
                    />
                  )}
                  <Icon
                    size={14}
                    strokeWidth={active ? 2.2 : 1.8}
                    className="relative z-10"
                    style={{ color: active ? 'var(--primary)' : undefined }}
                  />
                  <span className="relative z-10 hidden xl:inline">{label}</span>
                </button>
              )
            })}
          </div>
        </nav>

        <div className="flex shrink-0 items-center gap-0.5">
          {!isOnline && (
            <div
              className="mr-1 flex items-center gap-1.5 rounded-lg px-2 py-1 text-[10px] font-medium"
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
            <AnimatePresence mode="wait" initial={false}>
              <motion.span
                key={resolvedTheme}
                initial={{ opacity: 0, rotate: -20, scale: 0.8 }}
                animate={{ opacity: 1, rotate: 0, scale: 1 }}
                exit={{ opacity: 0, rotate: 20, scale: 0.8 }}
                transition={{ duration: 0.14 }}
                className="flex"
              >
                {resolvedTheme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
              </motion.span>
            </AnimatePresence>
          </button>

          {isAdmin && <div ref={settingsRef} className="relative">
            <button
              type="button"
              onClick={() => setShowSettings((value) => !value)}
              aria-label="Workspace settings"
              aria-expanded={showSettings}
              className={cn(
                'flex h-9 items-center gap-1.5 rounded-xl px-2 text-xs font-medium transition-colors duration-150',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
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

            <AnimatePresence>
              {showSettings && (
                <motion.div
                  initial={{ opacity: 0, y: -6, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: -6, scale: 0.98 }}
                  transition={{ duration: 0.15, ease: 'easeOut' }}
                  className="absolute right-0 top-full z-[1000] mt-2 w-[min(19rem,calc(100vw-1.5rem))] overflow-hidden rounded-2xl border"
                  style={{
                    background: 'var(--surface-elevated)',
                    borderColor: 'var(--border)',
                    boxShadow: 'var(--shadow-xl)',
                  }}
                  role="menu"
                >
                  <div className="border-b px-4 py-3" style={{ borderColor: 'var(--border)' }}>
                    <p className="text-sm font-semibold text-[var(--fg)]">Workspace settings</p>
                    <p className="mt-0.5 text-[11px] text-[var(--fg-soft)]">
                      Model runtime and system preferences
                    </p>
                  </div>

                  <div className="p-3">
                    <p className="label-xs mb-2 px-1">LLM implementation</p>
                    <div className="flex max-h-48 flex-col gap-1 overflow-y-auto">
                      {implementations.length > 0 ? implementations.map((impl) => {
                        const isActive = impl.name === currentImplementation
                        return (
                          <button
                            key={impl.name}
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation()
                              handleSwitchImplementation(impl.name)
                            }}
                            disabled={loading || isActive}
                            role="menuitem"
                            className={cn(
                              'flex w-full items-center justify-between rounded-xl border px-3 py-2.5 text-left text-xs font-medium',
                              'transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
                              isActive
                                ? 'border-[var(--border-focus)] bg-[var(--primary-soft)] text-[var(--primary)]'
                                : 'border-transparent text-[var(--fg-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--fg)]'
                            )}
                          >
                            <span>{impl.display_name || impl.name}</span>
                            {isActive && <Check size={13} />}
                          </button>
                        )
                      }) : (
                        <p className="px-3 py-2 text-xs text-[var(--fg-soft)]">No runtimes available</p>
                      )}
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 border-t p-3" style={{ borderColor: 'var(--border)' }}>
                    <button
                      type="button"
                      onClick={() => {
                        setActiveTab('memory')
                        setShowSettings(false)
                      }}
                      role="menuitem"
                      className="flex items-center justify-center gap-2 rounded-xl bg-[var(--surface-hover)] px-3 py-2.5 text-xs font-medium text-[var(--fg-muted)] transition-colors hover:text-[var(--fg)]"
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
                      className="flex items-center justify-center gap-2 rounded-xl bg-[var(--primary-soft)] px-3 py-2.5 text-xs font-medium text-[var(--primary)] transition-colors hover:bg-[var(--accent-soft)]"
                    >
                      <Settings2 size={13} /> All settings
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>}

          <span className="hidden max-w-32 truncate px-2 text-[10px] text-[var(--fg-soft)] 2xl:block" title={user?.email}>
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
