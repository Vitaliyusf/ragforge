/**
 * Training client for the direct finetuning REST surface.
 *
 * The current frontend talks to the finetuning service-local HTTP API on
 * port 8009 instead of routing training traffic through the shared gateway.
 */
import { get, post, del, upload } from '@/lib/http/client'
import { config } from '@/lib/config'

const BASE = config.trainingApiBaseUrl

class TrainingService {
  // Datasets
  async listDatasets() {
    return await get(`${BASE}/datasets`)
  }

  async uploadDataset(file, name, format = 'instruction') {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('name', name)
    formData.append('format', format)
    return await upload(`${BASE}/datasets`, formData)
  }

  async deleteDataset(datasetId) {
    return await del(`${BASE}/datasets/${datasetId}`)
  }

  // Jobs
  async listJobs() {
    return await get(`${BASE}/jobs`)
  }

  async getJob(jobId) {
    return await get(`${BASE}/jobs/${jobId}`)
  }

  async startTraining(datasetId, config = null) {
    const body = { dataset_id: datasetId }
    if (config) body.config = config
    return await post(`${BASE}/jobs`, body)
  }

  async cancelJob(jobId) {
    return await post(`${BASE}/jobs/${jobId}/cancel`)
  }

  // Adapters
  async listAdapters() {
    return await get(`${BASE}/adapters`)
  }

  async deleteAdapter(adapterId) {
    return await del(`${BASE}/adapters/${adapterId}`)
  }
}

export default new TrainingService()
