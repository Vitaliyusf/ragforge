/** Health service for system monitoring API calls */
import { get } from '@/lib/http/client'

class HealthService {
  async getDetailedHealth() {
    return await get('/v1/health/detailed')
  }

  async getServiceHealth(serviceName) {
    const data = await this.getDetailedHealth()
    return data.services?.[serviceName] || null
  }
}

export default new HealthService()
