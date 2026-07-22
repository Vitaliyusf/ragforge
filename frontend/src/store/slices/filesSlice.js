/**
 * filesSlice — persisted file list cache.
 *
 * Stores the last-fetched files list so the Files tab can render immediately
 * from cached state while the background poll fetches fresh data.
 */
import { createSlice } from '@reduxjs/toolkit'

const filesSlice = createSlice({
  name: 'files',
  initialState: {
    /** Last successfully fetched file records. */
    files: [],
    /** ISO timestamp of the last successful fetch, or null. */
    lastFetched: null,
  },
  reducers: {
    setFiles(state, action) {
      state.files = action.payload
      state.lastFetched = new Date().toISOString()
    },
    clearFiles(state) {
      state.files = []
      state.lastFetched = null
    },
  },
})

export const { setFiles, clearFiles } = filesSlice.actions
export default filesSlice.reducer

const EMPTY_FILES = []
export const selectCachedFiles = (state) => state.files?.files || EMPTY_FILES
export const selectFilesLastFetched = (state) => state.files?.lastFetched || null
