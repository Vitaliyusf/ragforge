import { createSlice } from '@reduxjs/toolkit'
import { LOG_SEVERITIES } from '@/lib/observability/deepLinks'

const initialState = {
  entries: [],
  selectedServices: ['gateway'], // Default to gateway
  lines: 100,
  autoRefresh: false,
  textFilter: '',
  // Every severity, i.e. no severity filter. The vocabulary is the
  // observability module's so a deep link cannot set one this slice rejects.
  severityFilter: [...LOG_SEVERITIES],
  pinnedToBottom: true
}

const logsSlice = createSlice({
  name: 'logs',
  initialState,
  reducers: {
    appendLogs: (state, action) => {
      const incoming = Array.isArray(action.payload) ? action.payload : [action.payload]
      state.entries = [...state.entries, ...incoming.filter(Boolean)].slice(-1000)
    },
    clearLogs: (state) => {
      state.entries = []
    },
    setSelectedServices: (state, action) => {
      // Ensure at least one service is selected
      const newServices = action.payload
      if (newServices.length > 0) {
        state.selectedServices = newServices
      }
    },
    toggleService: (state, action) => {
      const service = action.payload
      if (state.selectedServices.includes(service)) {
        const newServices = state.selectedServices.filter(s => s !== service)
        // Keep at least one selected
        state.selectedServices = newServices.length > 0 ? newServices : [service]
      } else {
        state.selectedServices = [...state.selectedServices, service]
      }
    },
    setLines: (state, action) => {
      state.lines = action.payload
    },
    setAutoRefresh: (state, action) => {
      state.autoRefresh = action.payload
    },
    setTextFilter: (state, action) => {
      state.textFilter = action.payload
    },
    setSeverityFilter: (state, action) => {
      // Ensure at least one severity is selected
      const newFilter = action.payload
      if (newFilter.length > 0) {
        state.severityFilter = newFilter
      }
    },
    toggleSeverity: (state, action) => {
      const severity = action.payload
      if (state.severityFilter.includes(severity)) {
        const newFilter = state.severityFilter.filter(s => s !== severity)
        // Keep at least one selected
        state.severityFilter = newFilter.length > 0 ? newFilter : [severity]
      } else {
        state.severityFilter = [...state.severityFilter, severity]
      }
    },
    setPinnedToBottom: (state, action) => {
      state.pinnedToBottom = action.payload
    },
    resetLogsState: (state) => {
      return initialState
    }
  }
})

export const {
  appendLogs,
  clearLogs,
  setSelectedServices,
  toggleService,
  setLines,
  setAutoRefresh,
  setTextFilter,
  setSeverityFilter,
  toggleSeverity,
  setPinnedToBottom,
  resetLogsState
} = logsSlice.actions

export default logsSlice.reducer
