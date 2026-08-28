/** Custom hook for log viewing */
'use client'

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
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
  const isMountedRef = useRef(true)

  useEffect(() => {
    isMountedRef.current = true
    return () => { isMountedRef.current = false }
  }, [])

  const fetchLogs = useCallback(async (service = null) => {
    setLoading(true)
    try {
      const serviceToFetch = service || selectedServices[0]
      const data = await logService.getLogs(serviceToFetch, lines)
      if (!isMountedRef.current) return
      setLogs(prev => ({
        ...prev,
        [serviceToFetch]: data
      }))
    } catch (error) {
      if (!isMountedRef.current) return
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
      if (isMountedRef.current) setLoading(false)
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
      if (!isMountedRef.current) return
      const newLogs = {}
      results.forEach((data, index) => {
        newLogs[selectedServices[index]] = data
      })
      setLogs(prev => ({ ...prev, ...newLogs }))
    } catch (error) {
      if (!isMountedRef.current) return
      console.error('Error fetching logs:', error)
    } finally {
      if (isMountedRef.current) setLoading(false)
    }
  }, [selectedServices, lines])

  const fetchAllLogs = useCallback(async () => {
    setLoading(true)
    try {
      const data = await logService.getAllLogs(lines)
      if (!isMountedRef.current) return
      setLogs(data)
    } catch (error) {
      if (!isMountedRef.current) return
      console.error('Error fetching all logs:', error)
    } finally {
      if (isMountedRef.current) setLoading(false)
    }
  }, [lines])

  useEffect(() => {
    if (selectedServices && selectedServices.length > 0) {
      fetchSelectedServicesLogs()
    }
  }, [selectedServices, lines, fetchSelectedServicesLogs])

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(() => {
        fetchSelectedServicesLogs()
      }, 2000)
      return () => clearInterval(interval)
    }
  }, [autoRefresh, selectedServices, lines, fetchSelectedServicesLogs])

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
