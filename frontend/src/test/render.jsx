import { render } from '@testing-library/react'
import { configureStore } from '@reduxjs/toolkit'
import { Provider } from 'react-redux'
import eventsReducer from '@/store/slices/eventsSlice'
import logsReducer from '@/store/slices/logsSlice'

export function createTestStore(preloadedState) {
  return configureStore({
    reducer: {
      events: eventsReducer,
      logs: logsReducer,
    },
    preloadedState,
  })
}

export function renderWithProviders(ui, options = {}) {
  const { store = createTestStore(), ...renderOptions } = options

  function Wrapper({ children }) {
    return <Provider store={store}>{children}</Provider>
  }

  return {
    store,
    ...render(ui, { wrapper: Wrapper, ...renderOptions }),
  }
}
