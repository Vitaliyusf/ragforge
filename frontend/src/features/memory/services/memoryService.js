/** Memory service for API calls */
import { get, post, put, del } from '@/lib/http/client'

class MemoryService {
  /**
   * Get all long-term memory entries
   * @returns {Promise<Object>} Memories data
   */
  async getMemories() {
    return await get('/v1/long-term-memory')
  }

  /**
   * Create a new long-term memory entry
   * @param {string} content - Memory content
   * @param {string|null} category - Optional category
   * @param {Object|null} metadata - Optional metadata
   * @returns {Promise<Object>} Created memory data
   */
  async createMemory(content, category = null, metadata = null) {
    const body = { content }
    if (category) body.category = category
    if (metadata) body.metadata = metadata
    return await post('/v1/long-term-memory', body)
  }

  /**
   * Update a long-term memory entry
   * @param {string} memoryId - Memory ID
   * @param {string|null} content - Optional new content
   * @param {string|null} category - Optional new category
   * @param {Object|null} metadata - Optional new metadata
   * @returns {Promise<Object>} Updated memory data
   */
  async updateMemory(memoryId, content = null, category = null, metadata = null) {
    const body = {}
    if (content !== null) body.content = content
    if (category !== null) body.category = category
    if (metadata !== null) body.metadata = metadata
    return await put(`/v1/long-term-memory/${memoryId}`, body)
  }

  /**
   * Delete a long-term memory entry
   * @param {string} memoryId - Memory ID
   * @returns {Promise<Object>} Response data
   */
  async deleteMemory(memoryId) {
    return await del(`/v1/long-term-memory/${memoryId}`)
  }
}

export default new MemoryService()
