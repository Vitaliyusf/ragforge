/**
 * eventsSlice — cross-component event bus via Redux.
 *
 * Replaces ad-hoc window.dispatchEvent / window.addEventListener patterns.
 * Consumers subscribe with useSelector; producers dispatch the action creators.
 */
import { createSlice } from '@reduxjs/toolkit'

const eventsSlice = createSlice({
  name: 'events',
  initialState: {
    /** Monotonically incrementing counter — any change means "files changed". */
    filesVersion: 0,
    /** Monotonically incrementing counter — any change means "a chat was deleted". */
    chatDeletedVersion: 0,
  },
  reducers: {
    /** Dispatch after a file is uploaded or deleted. */
    filesChanged(state) {
      state.filesVersion += 1
    },
    /** Dispatch after a chat is deleted. */
    chatDeleted(state) {
      state.chatDeletedVersion += 1
    },
  },
})

export const { filesChanged, chatDeleted } = eventsSlice.actions
export default eventsSlice.reducer
