import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import FilesTab from './FilesTab'

const API_BASE_URL = 'http://localhost:8000'

const STAGE_KEYS = [
  'extraction', 'review', 'chunking', 'summary',
  'embedding', 'semantic', 'vector', 'metadata',
]

function stages(overrides = {}) {
  return {
    ...Object.fromEntries(STAGE_KEYS.map((key) => [key, 'waiting'])),
    ...overrides,
  }
}

const READY_STAGES = Object.fromEntries(STAGE_KEYS.map((key) => [key, 'done']))

function createFile(overrides = {}) {
  return {
    file_id: 'file-1',
    document_id: 'file-1',
    filename: 'architecture.pdf',
    content_type: 'application/pdf',
    size: 2_400_000,
    status: 'complete',
    review_status: 'not_required',
    stage: READY_STAGES,
    created_at: '2026-08-29T09:00:00Z',
    updated_at: '2026-08-29T09:30:00Z',
    ...overrides,
  }
}

/** The three-row default fixture: one ready, one processing, one failed. */
function libraryFixture() {
  return [
    createFile(),
    createFile({
      file_id: 'file-2',
      document_id: 'file-2',
      filename: 'customer-data.xlsx',
      content_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      size: 8_100_000,
      status: 'processing',
      stage: stages({ extraction: 'done', chunking: 'done', embedding: 'running' }),
      updated_at: '2026-08-29T09:45:00Z',
    }),
    createFile({
      file_id: 'file-3',
      document_id: 'file-3',
      filename: 'manual.docx',
      content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      size: 900_000,
      status: 'error',
      stage: stages({ extraction: 'error' }),
      updated_at: '2026-08-29T09:15:00Z',
    }),
  ]
}

function rows() {
  return screen.getAllByTestId('document-row')
}

function rowNames() {
  return rows().map((row) => within(row).getAllByRole('button')[0].textContent)
}

describe('FilesTab documents table', () => {
  let files
  let deletedIds
  let rerunRequests

  beforeEach(() => {
    files = libraryFixture()
    deletedIds = []
    rerunRequests = []

    server.use(
      http.get(`${API_BASE_URL}/v1/files`, () => HttpResponse.json({ files })),
      http.get(`${API_BASE_URL}/v1/files/:fileId/audit-trail`, ({ params }) => {
        if (params.fileId !== 'file-3') return HttpResponse.json({ events: [], next_cursor: null })
        return HttpResponse.json({
          events: [
            {
              event_id: 'event-1',
              event_type: 'stage_failed',
              from_status: 'processing',
              to_status: 'error',
              task_id: 'task-3',
              reason: 'Extraction request timed out.',
              details: { chunk_count: 42 },
              actor: { display_name: 'files' },
              created_at: '2026-08-29T09:15:00Z',
            },
          ],
          next_cursor: null,
        })
      }),
      http.post(`${API_BASE_URL}/v1/files/:fileId/rerun`, ({ params, request }) => {
        const url = new URL(request.url)
        rerunRequests.push({ fileId: params.fileId, stage: url.searchParams.get('stage') })
        return HttpResponse.json({ status: 'success' })
      }),
      http.delete(`${API_BASE_URL}/v1/files/:fileId`, ({ params }) => {
        deletedIds.push(params.fileId)
        files = files.filter((file) => file.file_id !== params.fileId)
        return HttpResponse.json({ status: 'success' })
      })
    )
  })

  it('renders one row per document with type, size and updated columns', async () => {
    renderWithProviders(<FilesTab />)

    await waitFor(() => expect(rows()).toHaveLength(3))
    expect(screen.getByRole('columnheader', { name: 'Document' })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Pipeline' })).toBeInTheDocument()

    const readyRow = rows().find((row) => within(row).queryByText('architecture.pdf'))
    expect(within(readyRow).getByText('PDF · 2.29 MB')).toBeInTheDocument()
  })

  it('states a ready document once — "Ready" and "Indexed", not a stage tally', async () => {
    renderWithProviders(<FilesTab />)

    await waitFor(() => expect(rows()).toHaveLength(3))
    const readyRow = rows().find((row) => within(row).queryByText('architecture.pdf'))

    expect(within(readyRow).getByText('Ready')).toBeInTheDocument()
    expect(within(readyRow).getByText('Indexed')).toBeInTheDocument()
    expect(within(readyRow).queryByText('8/8')).not.toBeInTheDocument()
    expect(within(readyRow).queryByText(/Complete/)).not.toBeInTheDocument()
  })

  it('names the running stage on a processing row', async () => {
    renderWithProviders(<FilesTab />)

    await waitFor(() => expect(rows()).toHaveLength(3))
    const processingRow = rows().find((row) => within(row).queryByText('customer-data.xlsx'))

    expect(within(processingRow).getByText('Processing')).toBeInTheDocument()
    expect(within(processingRow).getByText('Embedding…')).toBeInTheDocument()
  })

  it('shows the failed stage on the row', async () => {
    renderWithProviders(<FilesTab />)

    await waitFor(() => expect(rows()).toHaveLength(3))
    const failedRow = rows().find((row) => within(row).queryByText('manual.docx'))

    expect(within(failedRow).getByText('Failed')).toBeInTheDocument()
    expect(within(failedRow).getByText('Extraction')).toBeInTheDocument()
  })

  it('searches by filename and reports the visible count', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)
    await waitFor(() => expect(rows()).toHaveLength(3))
    expect(screen.getByText('3 documents')).toBeInTheDocument()

    await user.type(screen.getByLabelText('Search documents'), 'manual')

    await waitFor(() => expect(rows()).toHaveLength(1))
    expect(screen.getByText('manual.docx')).toBeInTheDocument()
    expect(screen.getByText('1 of 3 documents')).toBeInTheDocument()
  })

  it('offers a way out when a search matches nothing', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)
    await waitFor(() => expect(rows()).toHaveLength(3))

    await user.type(screen.getByLabelText('Search documents'), 'nothing-matches-this')

    expect(await screen.findByText('No matching documents')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Clear filters/i }))
    await waitFor(() => expect(rows()).toHaveLength(3))
  })

  it('filters by the canonical status model', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)
    await waitFor(() => expect(rows()).toHaveLength(3))

    await user.click(screen.getByLabelText('Filter by status'))
    await user.click(await screen.findByRole('option', { name: /Failed/i }))

    await waitFor(() => expect(rows()).toHaveLength(1))
    expect(screen.getByText('manual.docx')).toBeInTheDocument()
  })

  it('sorts by name from the column header, and reverses on a second click', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)
    await waitFor(() => expect(rows()).toHaveLength(3))

    const nameHeader = screen.getByRole('button', { name: 'Document' })
    await user.click(nameHeader)
    await waitFor(() =>
      expect(rowNames()).toEqual(['manual.docx', 'customer-data.xlsx', 'architecture.pdf'])
    )

    await user.click(nameHeader)
    await waitFor(() =>
      expect(rowNames()).toEqual(['architecture.pdf', 'customer-data.xlsx', 'manual.docx'])
    )
  })

  it('sorts by updated time by default, newest first', async () => {
    renderWithProviders(<FilesTab />)
    await waitFor(() =>
      expect(rowNames()).toEqual(['customer-data.xlsx', 'architecture.pdf', 'manual.docx'])
    )
  })

  it('opens a drawer that explains the failure and offers a retry', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)
    await waitFor(() => expect(rows()).toHaveLength(3))

    await user.click(screen.getByText('manual.docx'))

    const drawer = await screen.findByRole('dialog')
    expect(within(drawer).getByText('Extraction failed')).toBeInTheDocument()
    // Stated twice on purpose: once as the failure banner's cause, once in
    // the activity entry it was read from.
    await waitFor(() =>
      expect(within(drawer).getAllByText('Extraction request timed out.').length).toBe(2)
    )
    expect(within(drawer).getByText('This document is not searchable.')).toBeInTheDocument()

    // Real ingestion activity and the chunk count carried on it.
    expect(within(drawer).getByText('stage failed')).toBeInTheDocument()
    expect(within(drawer).getByText('Chunks created:')).toBeInTheDocument()
    expect(within(drawer).getByText('42')).toBeInTheDocument()

    await user.click(within(drawer).getByRole('button', { name: /Retry ingestion/i }))
    await waitFor(() =>
      expect(rerunRequests).toEqual([{ fileId: 'file-3', stage: 'extraction' }])
    )
  })

  it('omits a Retrieval section, which the files API has no data for', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)
    await waitFor(() => expect(rows()).toHaveLength(3))

    await user.click(screen.getByText('architecture.pdf'))

    const drawer = await screen.findByRole('dialog')
    expect(within(drawer).getByText('Pipeline')).toBeInTheDocument()
    expect(within(drawer).queryByText('Retrieval')).not.toBeInTheDocument()
  })

  it('re-indexes a single row through the extraction stage the backend supports', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)
    await waitFor(() => expect(rows()).toHaveLength(3))

    await user.click(screen.getByRole('button', { name: 'Re-index architecture.pdf' }))

    await waitFor(() =>
      expect(rerunRequests).toEqual([{ fileId: 'file-1', stage: 'extraction' }])
    )
  })

  it('requires confirmation before deleting, and says what is removed', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)
    await waitFor(() => expect(rows()).toHaveLength(3))

    await user.click(screen.getByRole('button', { name: 'Delete manual.docx' }))

    expect(await screen.findByText('Delete this document?')).toBeInTheDocument()
    expect(
      screen.getByText(/"manual.docx" and its searchable index will be removed/i)
    ).toBeInTheDocument()
    expect(deletedIds).toEqual([])

    await user.click(screen.getByRole('button', { name: /^Delete$/ }))
    await waitFor(() => expect(deletedIds).toEqual(['file-3']))
  })

  it('runs a bulk delete over the selected rows after one confirmation', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)
    await waitFor(() => expect(rows()).toHaveLength(3))

    await user.click(screen.getByLabelText('Select all documents on this page'))
    expect(await screen.findByText('3 selected')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^Delete$/ }))
    expect(await screen.findByText('Delete 3 documents?')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Delete 3$/ }))
    await waitFor(() => expect(deletedIds.sort()).toEqual(['file-1', 'file-2', 'file-3']))
  })

  it('shows an uploaded document as a row in its real ingestion state', async () => {
    files = []
    server.use(
      http.post(`${API_BASE_URL}/v1/files/upload`, () => {
        files = [
          createFile({
            file_id: 'file-9',
            filename: 'policy.txt',
            content_type: 'text/plain',
            size: 128,
            status: 'processing',
            stage: stages({ extraction: 'running' }),
          }),
        ]
        return HttpResponse.json({ file_id: 'file-9', filename: 'policy.txt', status: 'started' })
      })
    )

    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)
    expect(await screen.findByText('No documents yet')).toBeInTheDocument()

    const input = screen.getByRole('button', { name: /Upload documents/i }).querySelector('input[type="file"]')
    await user.upload(input, new File(['body'], 'policy.txt', { type: 'text/plain' }))

    expect(await screen.findByText('policy.txt')).toBeInTheDocument()
    const row = rows()[0]
    expect(within(row).getByText('Processing')).toBeInTheDocument()
    expect(within(row).getByText('Extracting…')).toBeInTheDocument()
  })
})

describe('FilesTab at scale', () => {
  beforeEach(() => {
    // A deterministic 1,000-document library: every fourth document is in a
    // different lifecycle state, so filters and sorts have real work to do.
    const STATES = [
      { status: 'complete', stage: READY_STAGES },
      { status: 'processing', stage: stages({ extraction: 'done', embedding: 'running' }) },
      { status: 'error', stage: stages({ extraction: 'done', embedding: 'error' }) },
      { status: 'started', stage: stages() },
    ]
    const files = Array.from({ length: 1000 }, (_, index) => {
      const state = STATES[index % STATES.length]
      return createFile({
        file_id: `file-${index}`,
        document_id: `file-${index}`,
        filename: `document-${String(index).padStart(4, '0')}.pdf`,
        size: 1000 + index,
        updated_at: new Date(Date.UTC(2026, 7, 29, 0, 0, index)).toISOString(),
        ...state,
      })
    })
    server.use(http.get(`${API_BASE_URL}/v1/files`, () => HttpResponse.json({ files })))
  })

  it('pages a 1,000-document library and keeps search, filter and sort responsive', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)

    // One page of rows is mounted, and the counts still describe the whole set.
    await waitFor(() => expect(rows()).toHaveLength(50))
    expect(screen.getByText('1000 documents')).toBeInTheDocument()
    expect(screen.getByText('Showing 1–50 of 1000')).toBeInTheDocument()
    expect(screen.getByText('Page 1 of 20')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Next page' }))
    await waitFor(() => expect(screen.getByText('Showing 51–100 of 1000')).toBeInTheDocument())

    // Narrowing the view returns to the first page.
    await user.type(screen.getByLabelText('Search documents'), 'document-0777')
    await waitFor(() => expect(rows()).toHaveLength(1))
    expect(screen.getByText('1 of 1000 documents')).toBeInTheDocument()

    await user.clear(screen.getByLabelText('Search documents'))
    await waitFor(() => expect(rows()).toHaveLength(50))

    // The status filter reaches exactly the quarter of the library that failed.
    await user.click(screen.getByLabelText('Filter by status'))
    await user.click(await screen.findByRole('option', { name: /Failed/i }))
    await waitFor(() => expect(screen.getByText('250 of 1000 documents')).toBeInTheDocument())
    expect(rows()).toHaveLength(50)

    // Sorting reorders that subset, not just the page.
    await user.click(screen.getByRole('button', { name: 'Document' }))
    await waitFor(() => expect(rowNames()[0]).toBe('document-0998.pdf'))
  }, 60000)
})
