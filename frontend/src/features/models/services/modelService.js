/** Model management service for API calls */
import { get, post } from '@/lib/http/client'

class ModelService {
  /**
   * Get available LLM implementations
   * @returns {Promise<Object>} Implementations data
   */
  async getImplementations() {
    return await get('/v1/model-management/implementations')
  }

  /**
   * Get information about a specific implementation
   * @param {string} implementation - Implementation name
   * @returns {Promise<Object>} Implementation info
   */
  async getImplementationInfo(implementation) {
    return await get(`/v1/model-management/implementations/${implementation}`)
  }

  /**
   * List all models with details
   * @returns {Promise<Object>} Models data
   */
  async listAllModels() {
    return await get('/v1/model-management/models')
  }

  /**
   * Get detailed information about a specific model
   * @param {string} model - Model name
   * @returns {Promise<Object>} Model info
   */
  async getModelInfo(model) {
    return await get(`/v1/model-management/models/${encodeURIComponent(model)}`)
  }

  /**
   * Download a model
   * @param {string} model - Model name
   * @param {string} implementation - Implementation to use
   * @returns {Promise<Object>} Download response
   */
  async downloadModel(model, implementation = 'huggingface') {
    return await post(`/v1/model-management/models/${encodeURIComponent(model)}/download`, {
      implementation
    })
  }

  /**
   * Get download status for a model
   * @param {string} model - Model name
   * @returns {Promise<Object>} Download status
   */
  async getDownloadStatus(model) {
    return await get(`/v1/model-management/models/${encodeURIComponent(model)}/download-status`)
  }
}

export default new ModelService()
