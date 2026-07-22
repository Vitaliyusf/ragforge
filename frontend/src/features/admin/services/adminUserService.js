import { get, patch, post, put } from '@/lib/http/client'

class AdminUserService {
  listUsers() {
    return get('/v1/admin/users')
  }

  createUser(payload) {
    return post('/v1/admin/users', payload)
  }

  setStatus(userId, status) {
    return patch(`/v1/admin/users/${encodeURIComponent(userId)}/status`, { status })
  }

  resetPassword(userId, password) {
    return put(`/v1/admin/users/${encodeURIComponent(userId)}/password`, { password })
  }
}

export default new AdminUserService()
