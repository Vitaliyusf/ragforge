/** Hook for managing training state */
import { useState, useEffect, useCallback, useRef } from 'react'
import trainingService from '../services/trainingService'

export function useTraining() {
  const [datasets, setDatasets] = useState([])
  const [jobs, setJobs] = useState([])
  const [adapters, setAdapters] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const intervalRef = useRef(null)

  const fetchAll = useCallback(async () => {
    try {
      const [dsRes, jobsRes, adaptersRes] = await Promise.all([
        trainingService.listDatasets().catch(() => ({ datasets: [] })),
        trainingService.listJobs().catch(() => ({ jobs: [] })),
        trainingService.listAdapters().catch(() => ({ adapters: [] })),
      ])
      setDatasets(dsRes.datasets || [])
      setJobs(jobsRes.jobs || [])
      setAdapters(adaptersRes.adapters || [])
      setError(null)
    } catch (err) {
      setError(err.message || 'Failed to load training data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
    intervalRef.current = setInterval(fetchAll, 5000)
    return () => clearInterval(intervalRef.current)
  }, [fetchAll])

  const uploadDataset = useCallback(async (file, name, format) => {
    const result = await trainingService.uploadDataset(file, name, format)
    await fetchAll()
    return result
  }, [fetchAll])

  const deleteDataset = useCallback(async (datasetId) => {
    await trainingService.deleteDataset(datasetId)
    await fetchAll()
  }, [fetchAll])

  const startTraining = useCallback(async (datasetId, config) => {
    const result = await trainingService.startTraining(datasetId, config)
    await fetchAll()
    return result
  }, [fetchAll])

  const cancelJob = useCallback(async (jobId) => {
    await trainingService.cancelJob(jobId)
    await fetchAll()
  }, [fetchAll])

  const deleteAdapter = useCallback(async (adapterId) => {
    await trainingService.deleteAdapter(adapterId)
    await fetchAll()
  }, [fetchAll])

  const activeJob = jobs.find(
    (j) => ['queued', 'preparing', 'training', 'saving'].includes(j.status)
  )

  return {
    datasets,
    jobs,
    adapters,
    activeJob,
    loading,
    error,
    uploadDataset,
    deleteDataset,
    startTraining,
    cancelJob,
    deleteAdapter,
    refresh: fetchAll,
  }
}
