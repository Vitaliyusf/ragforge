/**
 * The Logs screen in Hebrew.
 *
 * The rule this pins is the one that is easy to get backwards: the screen's
 * chrome is copy and follows the interface, while the output viewport is a
 * technical artifact and never does. A reordered log line is destroyed
 * evidence — the severity, the origin path and the message ordering all carry
 * meaning that the bidi algorithm would rearrange.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Provider } from 'react-redux'

import LogsTab from './LogsTab'
import { I18nProvider } from '@/i18n'
import { createTestStore } from '@/test/render'

const LOG_LINE = '2026-08-28 23:02:11 INFO rag.retrieval chunk_id=chunk-7 latency=812ms'

vi.mock('@/features/logs', () => ({
  useLogs: () => ({
    logs: { rag: { logs: [{ line: LOG_LINE, index: 0 }] } },
    loading: false,
    services: ['rag'],
    filteredLogs: [{ service: 'rag', index: 0, line: LOG_LINE, severity: 'info' }],
    fetchSelectedServicesLogs: vi.fn(),
    fetchAllLogs: vi.fn(),
    clearLogs: vi.fn(),
  }),
}))

function renderLogs(locale = 'he') {
  const store = createTestStore({
    logs: {
      selectedServices: ['rag'],
      lines: 100,
      autoRefresh: true,
      textFilter: '',
      severityFilter: ['error', 'warning', 'info', 'debug', 'trace', 'unknown'],
      pinnedToBottom: true,
    },
  })
  return render(
    <Provider store={store}>
      <I18nProvider initialLocale={locale}>
        <LogsTab />
      </I18nProvider>
    </Provider>
  )
}

describe('logs screen chrome', () => {
  it('translates the headings, filters and stream controls', () => {
    renderLogs('he')
    expect(screen.getByRole('heading', { name: 'לוגים חיים' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'שירותים' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'סינון הפלט' })).toBeInTheDocument()
    expect(screen.getByText('חומרה')).toBeInTheDocument()
    expect(screen.getByLabelText('ניקוי הלוגים')).toBeInTheDocument()
  })

  it('keeps the English screen unchanged', () => {
    renderLogs('en')
    expect(screen.getByRole('heading', { name: 'Live logs' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Services' })).toBeInTheDocument()
  })
})

describe('log output viewport', () => {
  it('stays left-to-right and left-aligned inside the Hebrew shell', () => {
    renderLogs('he')
    const row = screen.getByText(new RegExp('chunk_id=chunk-7')).closest('[dir="ltr"]')
    expect(row).not.toBeNull()
    expect(row.className).toContain('text-left')
    expect(row.className).toContain('unicode-bidi:isolate')
  })

  it('does not translate the log line itself', () => {
    renderLogs('he')
    expect(screen.getByText(new RegExp('rag.retrieval'))).toBeInTheDocument()
  })

  it('keeps the canonical service name in English on both sides of the screen', () => {
    renderLogs('he')
    // "RAG Orchestrator" is a deployable service's name, not copy. It has no
    // Hebrew form, and inventing one would break the operator's ability to
    // match it against compose files and dashboards.
    const names = screen.getAllByText('RAG Orchestrator')
    expect(names.length).toBeGreaterThan(0)
    for (const name of names) {
      expect(name).toHaveAttribute('dir', 'ltr')
    }
  })
})
