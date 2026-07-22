import { combineReducers, configureStore } from '@reduxjs/toolkit'
import logsReducer from './slices/logsSlice'
import eventsReducer from './slices/eventsSlice'
import filesReducer from './slices/filesSlice'

const appReducer = combineReducers({
    logs: logsReducer,
    events: eventsReducer,
    files: filesReducer,
})

const rootReducer = (state, action) => {
  if (action.type === 'auth/sessionChanged') return appReducer(undefined, action)
  return appReducer(state, action)
}

export const store = configureStore({
  reducer: rootReducer,
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: [
          'auth/sessionChanged',
        ],
      },
    }),
})
