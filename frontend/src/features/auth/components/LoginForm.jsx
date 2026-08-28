/** Login form component with first-run administrator setup */
'use client'

import { useEffect, useState } from 'react'
import { LogIn, ShieldCheck } from 'lucide-react'
import { useAuth } from '@/features/auth/hooks/useAuth'
import authService from '@/features/auth/services/authService'
import Input from '@/components/ui/Input'
import Button from '@/components/ui/Button'

const MIN_PASSWORD_LENGTH = 15

export default function LoginForm() {
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
          setFormError(`Password must contain at least ${MIN_PASSWORD_LENGTH} characters`)
          return
        }
        if (password !== confirmPassword) {
          setFormError('Passwords do not match')
          return
        }
        await setup(email, displayName || 'Administrator', password)
      } else {
        await login(tenant, email, password)
      }
    } catch (err) {
      // Error is handled by useAuth hook
    }
  }

  const isSetup = mode === 'setup'

  return (
    <div className="min-h-screen flex">
      <div className="hidden lg:flex flex-1 bg-gradient-primary items-center justify-center p-12">
        <div className="max-w-md text-white">
          <h2 className="text-3xl font-bold mb-4">RAGForge</h2>
          <p className="text-white/90 text-xl">
            Your intelligent assistant for document search, chat, and more.
          </p>
          <div className="mt-8 flex gap-4">
            <div className="w-12 h-12 rounded-xl bg-white/20 flex items-center justify-center">
              {isSetup ? <ShieldCheck size={24} /> : <LogIn size={24} />}
            </div>
            <div>
              <p className="font-semibold">Secure access</p>
              <p className="text-[15px] text-white/80">
                {isSetup ? 'Set up your workspace to get started' : 'Sign in to get started'}
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
              {isSetup ? 'Create administrator' : 'Welcome back'}
            </h2>
            <p className="text-text-muted text-[15px] mt-1">
              {isSetup
                ? 'This is a fresh installation. The account you create now becomes the workspace administrator.'
                : 'Sign in to your account'}
            </p>
          </div>

          {(formError || error) && (
            <div className="p-4 rounded-xl bg-danger-soft border border-danger text-danger dark:text-danger text-[15px]">
              {formError || error}
            </div>
          )}

          {!isSetup && (
            <div>
              <label className="block text-text-secondary text-[15px] mb-2">Workspace</label>
              <Input
                type="text"
                value={tenant}
                onChange={(e) => setTenant(e.target.value)}
                placeholder="default"
                autoComplete="organization"
                required
              />
            </div>
          )}

          {isSetup && (
            <div>
              <label className="block text-text-secondary text-[15px] mb-2">Display name</label>
              <Input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="Administrator"
                autoComplete="name"
              />
            </div>
          )}

          <div>
            <label className="block text-text-secondary text-[15px] mb-2">Email</label>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="username"
              required
            />
          </div>

          <div>
            <label className="block text-text-secondary text-[15px] mb-2">Password</label>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete={isSetup ? 'new-password' : 'current-password'}
              minLength={isSetup ? MIN_PASSWORD_LENGTH : undefined}
              required
            />
            {isSetup && (
              <p className="text-text-muted text-[13px] mt-1">
                At least {MIN_PASSWORD_LENGTH} characters.
              </p>
            )}
          </div>

          {isSetup && (
            <div>
              <label className="block text-text-secondary text-[15px] mb-2">Confirm password</label>
              <Input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
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
            {!loading && (isSetup ? 'Create administrator' : 'Sign in')}
          </Button>
        </form>
      </div>
    </div>
  )
}
