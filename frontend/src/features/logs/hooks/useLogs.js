/** Custom hook for log viewing */
'use client'

import { useState, useEffect, useEffectEvent, useCallback, useMemo } from 'react'
import logService from '@/features/logs/services/logService'
import { detectLogSeverity } from '@/lib/formatting/logs'

export function useLogs(
  selectedServices = ['gateway'],
  lines = 100,
  autoRefresh = false,
  textFilter = '',
  severityFilter = ['error', 'warning', 'info', 'debug', 'trace', 'unknown']
) {
  const services = ['gateway', 'files', 'embedding', 'llm_agent', 'memory', 'rag', 'reranker', 'vector_db']
  const [logs, setLogs] = useState({})
  const [loading, setLoading] = useState(false)

  const fetchLogs = useCallback(async (service = null) => {
    setLoading(true)
    try {
      const serviceToFetch = service || selectedServices[0]
      const data = await logService.getLogs(serviceToFetch, lines)
      setLogs(prev => ({
        ...prev,
        [serviceToFetch]: data
      }))
    } catch (error) {
      console.error('Error fetching logs:', error)
      setLogs(prev => ({
        ...prev,
        [selectedServices[0]]: {
          service: selectedServices[0],
          logs: [`Error fetching logs: ${error.message}`],
          source: 'error'
        }
      }))
    } finally {
      setLoading(false)
    }
  }, [selectedServices, lines])

  const fetchSelectedServicesLogs = useCallback(async () => {
    setLoading(true)
    try {
      const promises = selectedServices.map(service =>
        logService.getLogs(service, lines).catch(error => ({
          service,
          logs: [`Error fetching logs: ${error.message}`],
          source: 'error'
        }))
      )
      const results = await Promise.all(promises)
      const newLogs = {}
      results.forEach((data, index) => {
        newLogs[selectedServices[index]] = data
      })
      setLogs(prev => ({ ...prev, ...newLogs }))
    } catch (error) {
      console.error('Error fetching logs:', error)
    } finally {
      setLoading(false)
    }
  }, [selectedServices, lines])

  const fetchAllLogs = useCallback(async () => {
    setLoading(true)
    try {
      const data = await logService.getAllLogs(lines)
      setLogs(data)
    } catch (error) {
      console.error('Error fetching all logs:', error)
    } finally {
      setLoading(false)
    }
  }, [lines])

  useEffect(() => {
    if (selectedServices && selectedServices.length > 0) {
      fetchSelectedServicesLogs()
    }
    // `fetchSelectedServicesLogs` already closes over `selectedServices` and
    // `lines`; listing them again only duplicated the trigger.
  }, [fetchSelectedServicesLogs, selectedServices])

  // The poll always calls the newest fetcher, but is not *reactive* to it: the
  // 2s timer now belongs to `autoRefresh` alone, so changing the service
  // selection or the line count no longer tears the interval down and starts a
  // fresh one (which reset the phase and could double-fetch on the seam).
  const pollLogs = useEffectEvent(() => {
    fetchSelectedServicesLogs()
  })

  useEffect(() => {
    if (!autoRefresh) return undefined
    const interval = setInterval(() => pollLogs(), 2000)
    return () => clearInterval(interval)
  }, [autoRefresh])

  const filteredLogs = useMemo(() => {
    const result = []
    
    selectedServices.forEach(service => {
      const serviceLogs = logs[service]?.logs || []
      serviceLogs.forEach((line, index) => {
        const severity = detectLogSeverity(line)
        
        if (!severityFilter.includes(severity)) {
          return
        }
        
        if (textFilter && !line.toLowerCase().includes(textFilter.toLowerCase())) {
          return
        }
        
        result.push({
          service,
          line,
          severity,
          index,
          originalIndex: index
        })
      })
    })
    
    return result
  }, [logs, selectedServices, textFilter, severityFilter])

  const clearLogs = useCallback(() => {
    setLogs({})
  }, [])

  return {
    logs,
    loading,
    services,
    filteredLogs,
    fetchLogs,
    fetchSelectedServicesLogs,
    fetchAllLogs,
    clearLogs
  }
}
