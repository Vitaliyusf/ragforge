/** Hook for polling system health data */
import { useState, useEffect, useCallback, useRef } from 'react'
import healthService from '../services/healthService'

const POLL_INTERVAL = 5000

export function useHealth() {
  const [health, setHealth] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [history, setHistory] = useState([])
  const intervalRef = useRef(null)

  const fetchHealth = useCallback(async () => {
    try {
      const data = await healthService.getDetailedHealth()
      setHealth(data)
      setError(null)
      setHistory((prev) => {
        const next = [...prev, { timestamp: Date.now(), data }]
        return next.length > 60 ? next.slice(-60) : next
      })
    } catch (err) {
      setError(err.message || 'Failed to fetch health data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchHealth()
    intervalRef.current = setInterval(fetchHealth, POLL_INTERVAL)
    return () => clearInterval(intervalRef.current)
  }, [fetchHealth])

  const refresh = useCallback(() => {
    setLoading(true)
    fetchHealth()
  }, [fetchHealth])

  return { health, loading, error, history, refresh }
}
