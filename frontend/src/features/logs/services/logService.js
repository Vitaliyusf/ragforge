/** Log service for API calls */
import { get } from '@/lib/http/client'

class LogService {
  /**
   * Get logs for a specific service
   * @param {string} service - Service name
   * @param {number} lines - Number of lines to retrieve
   * @returns {Promise<Object>} Logs data
   */
  async getLogs(service, lines = 100) {
    return await get(`/v1/logs/${service}?lines=${lines}`)
  }

  /**
   * Get logs from all services
   * @param {number} lines - Number of lines per service
   * @returns {Promise<Object>} All logs data
   */
  async getAllLogs(lines = 50) {
    return await get(`/v1/logs?lines=${lines}`)
  }
}

export default new LogService()
