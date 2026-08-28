/** File service for gateway HTTP APIs */
import { del, get, post, upload } from '@/lib/http/client'

class FileService {
  async getFiles() {
    return await get('/v1/files')
  }

  async getMyFiles() {
    return await get('/v1/files/mine')
  }

  async getSuggestedQuestions() {
    return await get('/v1/files/suggested-questions')
  }

  async uploadFile(file) {
    const formData = new FormData()
    formData.append('file', file)
    return await upload('/v1/files/upload', formData)
  }

  async getReviewCase(fileId) {
    return await get(`/v1/files/${fileId}/review-case`)
  }

  async submitReviewDecision(fileId, payload) {
    return await post(`/v1/files/${fileId}/review-decision`, payload)
  }

  async getAuditTrail(fileId, options = {}) {
    const params = new URLSearchParams()
    if (options.cursor) params.set('cursor', options.cursor)
    if (options.limit) params.set('limit', String(options.limit))
    const suffix = params.toString() ? `?${params.toString()}` : ''
    return await get(`/v1/files/${fileId}/audit-trail${suffix}`)
  }

  async deleteFile(fileId) {
    return await del(`/v1/files/${fileId}`)
  }
}

export default new FileService()
