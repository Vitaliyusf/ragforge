/** Read-only effective-configuration API client. */
import { get } from '@/lib/http/client'

class ConfigService {
  /**
   * Get current configuration
   * @returns {Promise<Object>} Configuration data
   */
  async getConfig() {
    return await get('/v1/config')
  }

}

export default new ConfigService()
