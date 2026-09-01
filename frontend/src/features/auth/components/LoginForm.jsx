/** Login form component with first-run administrator setup */
'use client'

import { useEffect, useState } from 'react'
import { LogIn, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/features/auth/hooks/useAuth'
import authService from '@/features/auth/services/authService'
import Input from '@/components/ui/Input'
import Button from '@/components/ui/Button'
import LanguageSwitcher from '@/components/layout/LanguageSwitcher'
import { useI18n } from '@/i18n'

const MIN_PASSWORD_LENGTH = 15

export default function LoginForm() {
  const { t } = useI18n()
  const { login, setup, loading, error } = useAuth()
  const [mode, setMode] = useState('login') // 'login' | 'setup'
  const [tenant, setTenant] = useState('default')
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [formError, setFormError] = useState(null)

  useEffect(() => {
    let active = true
    authService.getSetupStatus()
      .then((response) => {
        if (active && response?.needs_setup) setMode('setup')
      })
      .catch(() => {
        // Gateway unavailable or setup already completed — keep the login form.
      })
    return () => { active = false }
  }, [])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setFormError(null)
    try {
      if (mode === 'setup') {
        if (password.length < MIN_PASSWORD_LENGTH) {
          setFormError(t('auth.passwordTooShort', { count: MIN_PASSWORD_LENGTH }))
          return
        }
        if (password !== confirmPassword) {
          setFormError(t('auth.passwordMismatch'))
          return
        }
        await setup(email, displayName || t('auth.administrator'), password)
      } else {
        await login(tenant, email, password)
      }
    } catch (err) {
      // Error is handled by useAuth hook
    }
  }

  const isSetup = mode === 'setup'

  return (
    // The language control is mounted here as well as in the header: a
    // reader who cannot read the sign-in form cannot sign in to reach the
    // setting that would fix it.
    <div className="relative min-h-screen flex">
      <div className="absolute top-4 end-4 z-10">
        <LanguageSwitcher
          buttonClassName={[
            'relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl',
            'text-[var(--fg-muted)] transition-colors duration-150',
            'hover:bg-[var(--surface-hover)] hover:text-[var(--fg)]',
            'focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
          ].join(' ')}
        />
      </div>
      <div className="hidden lg:flex flex-1 bg-gradient-primary items-center justify-center p-12">
        <div className="max-w-md text-white">
          {/* The brand mark is a proper noun and stays LTR in every locale. */}
          <h2 dir="ltr" className="text-3xl font-bold mb-4 [unicode-bidi:isolate]">RAGForge</h2>
          <p className="text-white/90 text-xl">{t('auth.marketing')}</p>
          <div className="mt-8 flex gap-4">
            <div className="w-12 h-12 rounded-xl bg-white/20 flex items-center justify-center">
              {isSetup ? <ShieldCheck size={24} /> : <LogIn size={24} />}
            </div>
            <div>
              <p className="font-semibold">{t('auth.secureAccess')}</p>
              <p className="text-[15px] text-white/80">
                {t(isSetup ? 'auth.setupCta' : 'auth.signInCta')}
              </p>
            </div>
          </div>
        </div>
      </div>
      <div className="flex-1 flex items-center justify-center p-8 bg-bg-primary">
        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-5 p-8 rounded-2xl border border-border bg-bg-elevated shadow-lg w-full max-w-[400px]"
        >
          <div className="mb-2">
            <h2 className="text-2xl font-semibold text-text-primary">
              {t(isSetup ? 'auth.createAdministrator' : 'auth.welcomeBack')}
            </h2>
            <p className="text-text-muted text-[15px] mt-1">
              {t(isSetup ? 'auth.setupSubtitle' : 'auth.signInSubtitle')}
            </p>
          </div>

          {(formError || error) && (
            <div className="p-4 rounded-xl bg-danger-soft border border-danger text-danger dark:text-danger text-[15px]">
              {formError || error}
            </div>
          )}

          {!isSetup && (
            <div>
              <label className="block text-text-secondary text-[15px] mb-2">{t('auth.workspace')}</label>
              {/* A workspace id is a backend identifier, not copy. */}
              <Input
                type="text"
                dir="ltr"
                value={tenant}
                onChange={(e) => setTenant(e.target.value)}
                placeholder="default"
                aria-label={t('auth.workspace')}
                autoComplete="organization"
                required
              />
            </div>
          )}

          {isSetup && (
            <div>
              <label className="block text-text-secondary text-[15px] mb-2">{t('auth.displayName')}</label>
              <Input
                type="text"
                dir="auto"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder={t('auth.administrator')}
                aria-label={t('auth.displayName')}
                autoComplete="name"
              />
            </div>
          )}

          <div>
            <label className="block text-text-secondary text-[15px] mb-2">{t('auth.email')}</label>
            {/* An address is never Hebrew: LTR in both locales. */}
            <Input
              type="email"
              dir="ltr"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              aria-label={t('auth.email')}
              autoComplete="username"
              required
            />
          </div>

          <div>
            <label className="block text-text-secondary text-[15px] mb-2">{t('auth.password')}</label>
            <Input
              type="password"
              dir="ltr"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              aria-label={t('auth.password')}
              autoComplete={isSetup ? 'new-password' : 'current-password'}
              minLength={isSetup ? MIN_PASSWORD_LENGTH : undefined}
              required
            />
            {isSetup && (
              <p className="text-text-muted text-[13px] mt-1">
                {t('auth.passwordHint', { count: MIN_PASSWORD_LENGTH })}
              </p>
            )}
          </div>

          {isSetup && (
            <div>
              <label className="block text-text-secondary text-[15px] mb-2">{t('auth.confirmPassword')}</label>
              <Input
                type="password"
                dir="ltr"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                aria-label={t('auth.confirmPassword')}
                autoComplete="new-password"
                minLength={MIN_PASSWORD_LENGTH}
                required
              />
            </div>
          )}

          <Button
            type="submit"
            variant="primary"
            disabled={loading}
            loading={loading}
            className="w-full py-3"
          >
            {!loading && t(isSetup ? 'auth.createAdministrator' : 'auth.signIn')}
          </Button>
        </form>
      </div>
    </div>
  )
}
