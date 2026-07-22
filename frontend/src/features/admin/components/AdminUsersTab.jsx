'use client'

import { useCallback, useEffect, useState } from 'react'
import { UserPlus, Users } from 'lucide-react'
import adminUserService from '@/features/admin/services/adminUserService'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'

export default function AdminUsersTab() {
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
      setError(loadError?.message || 'Failed to load users')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadUsers() }, [loadUsers])

  const createUser = async (event) => {
    event.preventDefault()
    setError(null)
    try {
      await adminUserService.createUser(form)
      setForm({ email: '', display_name: '', password: '' })
      await loadUsers()
    } catch (createError) {
      setError(createError?.message || 'Failed to create user')
    }
  }

  const toggleStatus = async (user) => {
    try {
      await adminUserService.setStatus(user.user_id, user.status === 'active' ? 'disabled' : 'active')
      await loadUsers()
    } catch (statusError) {
      setError(statusError?.message || 'Failed to update user')
    }
  }

  return (
    <section className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-[var(--fg)]">
            <Users size={22} /> Users
          </h1>
          <p className="mt-1 text-sm text-[var(--fg-soft)]">Manage users assigned to your administrator account.</p>
        </div>

        <form onSubmit={createUser} className="grid gap-3 rounded-2xl border p-4 md:grid-cols-4" style={{ borderColor: 'var(--border)', background: 'var(--surface-elevated)' }}>
          <Input type="text" value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} placeholder="Display name" required />
          <Input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} placeholder="user@example.com" required />
          <Input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} placeholder="Temporary password (15+)" minLength={15} required />
          <Button type="submit" variant="primary"><UserPlus size={15} /> Add user</Button>
        </form>

        {error && <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-500">{error}</div>}

        <div className="overflow-hidden rounded-2xl border" style={{ borderColor: 'var(--border)', background: 'var(--surface-elevated)' }}>
          {loading ? <p className="p-5 text-sm text-[var(--fg-soft)]">Loading users…</p> : users.map((user) => (
            <div key={user.user_id} className="flex items-center justify-between gap-4 border-b p-4 last:border-b-0" style={{ borderColor: 'var(--border)' }}>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-[var(--fg)]">{user.display_name}</p>
                <p className="truncate text-xs text-[var(--fg-soft)]">{user.email} · {user.role}</p>
              </div>
              {user.role !== 'admin' && (
                <Button type="button" variant="secondary" onClick={() => toggleStatus(user)}>
                  {user.status === 'active' ? 'Disable' : 'Enable'}
                </Button>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
