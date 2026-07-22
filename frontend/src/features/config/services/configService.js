/** Configuration management service for API calls */
import { get, post } from '@/lib/http/client'

class ConfigService {
  /**
   * Get current configuration
   * @returns {Promise<Object>} Configuration data
   */
  async getConfig() {
    return await get('/v1/config')
  }

  /**
   * Update configuration
   * @param {Object} updates - Configuration updates
   * @returns {Promise<Object>} Update response
   */
  async updateConfig(updates) {
    return await post('/v1/config', updates)
  }

  /**
   * Get generation parameters
   * @returns {Promise<Object>} Generation parameters
   */
  async getGenerationParams() {
    return await get('/v1/config/generation-params')
  }

  /**
   * Update generation parameters
   * @param {Object} params - Generation parameters
   * @returns {Promise<Object>} Update response
   */
  async updateGenerationParams(params) {
    return await post('/v1/config/generation-params', params)
  }

  /**
   * Switch LLM implementation
   * @param {string} implementation - Implementation name
   * @returns {Promise<Object>} Switch response
   */
  async switchImplementation(implementation) {
    return await post(`/v1/config/switch-implementation?implementation=${encodeURIComponent(implementation)}`)
  }

  /**
   * Get model configurations
   * @returns {Promise<Object>} Model configurations
   */
  async getModelConfigs() {
    return await get('/v1/config/models')
  }

  /**
   * Update model configurations
   * @param {Object} modelConfigs - Model configurations
   * @returns {Promise<Object>} Update response
   */
  async updateModelConfigs(modelConfigs) {
    return await post('/v1/config/models', modelConfigs)
  }
}

export default new ConfigService()
