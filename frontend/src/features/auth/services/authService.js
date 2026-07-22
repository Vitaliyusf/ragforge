/** Authentication service for API calls */
import { get, post } from '@/lib/http/client'

class AuthService {
  /**
   * Login user
   * @param {string} email - User email
   * @param {string} password - User password
   * @returns {Promise<Object>} Auth response
   */
  async login(tenant, email, password) {
    return await post('/v1/auth/login', {
      tenant,
      email,
      password
    })
  }

  /**
   * Check whether the first-run administrator setup is still open
   * @returns {Promise<Object>} { needs_setup }
   */
  async getSetupStatus() {
    return await get('/v1/auth/setup', { retries: 0 })
  }

  /**
   * Create the first administrator account (first run only)
   * @param {string} email - Administrator email
   * @param {string} displayName - Administrator display name
   * @param {string} password - Administrator password
   * @returns {Promise<Object>} Auth response
   */
  async setup(email, displayName, password) {
    return await post('/v1/auth/setup', {
      email,
      display_name: displayName,
      password
    })
  }

  /**
   * Logout user
   * @returns {Promise<Object>} Logout response
   */
  async logout() {
    return await post('/v1/auth/logout')
  }

  /**
   * Get current user
   * @returns {Promise<Object>} User data
   */
  async getCurrentUser() {
    return await get('/v1/auth/me', { retries: 0 })
  }

  async getSocketTicket() {
    return await post('/v1/auth/socket-ticket')
  }
}

export default new AuthService()
