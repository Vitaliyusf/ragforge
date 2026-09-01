'use client'

import { useCallback, useEffect, useState } from 'react'
import { UserPlus, Users } from 'lucide-react'
import adminUserService from '@/features/admin/services/adminUserService'
import Button from '@/components/ui/Button'
import LoadingState from '@/components/feedback/LoadingState'
import Input from '@/components/ui/Input'
import TechnicalText from '@/components/ui/TechnicalText'
import { useI18n } from '@/i18n'

export default function AdminUsersTab() {
  const { t } = useI18n()
  const [users, setUsers] = useState([])
  const [form, setForm] = useState({ email: '', display_name: '', password: '' })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadUsers = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setUsers(await adminUserService.listUsers())
    } catch (loadError) {
      setError(loadError?.message || t('users.loadFailed'))
    } finally {
      setLoading(false)
    }
  }, [t])

  useEffect(() => { loadUsers() }, [loadUsers])

  const createUser = async (event) => {
    event.preventDefault()
    setError(null)
    try {
      await adminUserService.createUser(form)
      setForm({ email: '', display_name: '', password: '' })
      await loadUsers()
    } catch (createError) {
      setError(createError?.message || t('users.createFailed'))
    }
  }

  const toggleStatus = async (user) => {
    try {
      await adminUserService.setStatus(user.user_id, user.status === 'active' ? 'disabled' : 'active')
      await loadUsers()
    } catch (statusError) {
      setError(statusError?.message || t('users.updateFailed'))
    }
  }

  return (
    <section className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-[var(--fg)]">
            <Users size={22} /> {t('users.title')}
          </h1>
          <p className="mt-1 text-[15px] text-[var(--fg-soft)]">{t('users.description')}</p>
        </div>

        <form onSubmit={createUser} className="grid gap-3 rounded-2xl border p-4 md:grid-cols-4" style={{ borderColor: 'var(--border)', background: 'var(--surface-elevated)' }}>
          {/* A display name may be Hebrew or English; an email address and a
              password are neither, and stay LTR in both locales. */}
          <Input
            type="text"
            value={form.display_name}
            onChange={(event) => setForm({ ...form, display_name: event.target.value })}
            placeholder={t('users.displayName')}
            aria-label={t('users.displayName')}
            dir="auto"
            required
          />
          <Input
            type="email"
            dir="ltr"
            value={form.email}
            onChange={(event) => setForm({ ...form, email: event.target.value })}
            placeholder={t('users.emailPlaceholder')}
            aria-label={t('auth.email')}
            required
          />
          <Input
            type="password"
            dir="ltr"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
            placeholder={t('users.temporaryPassword')}
            aria-label={t('users.temporaryPassword')}
            minLength={15}
            required
          />
          <Button type="submit" variant="primary"><UserPlus size={15} /> {t('users.add')}</Button>
        </form>

        {error && <div className="rounded-xl border border-danger bg-danger-soft p-3 text-[15px] text-danger">{error}</div>}

        <div className="overflow-hidden rounded-2xl border" style={{ borderColor: 'var(--border)', background: 'var(--surface-elevated)' }}>
          {loading ? <LoadingState label={t('users.loading')} /> : users.map((user) => (
            <div key={user.user_id} className="flex items-center justify-between gap-4 border-b p-4 last:border-b-0" style={{ borderColor: 'var(--border)' }}>
              <div className="min-w-0">
                <p dir="auto" className="truncate text-start text-[15px] font-medium text-[var(--fg)]">
                  {user.display_name}
                </p>
                {/* Email and role are backend values: the address must not be
                    reordered, and the role is an authorization value, not copy. */}
                <TechnicalText className="truncate text-[13px] text-[var(--fg-soft)]">
                  {user.email} · {user.role}
                </TechnicalText>
              </div>
              {user.role !== 'admin' && (
                <Button type="button" variant="secondary" onClick={() => toggleStatus(user)}>
                  {t(user.status === 'active' ? 'users.disable' : 'users.enable')}
                </Button>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
