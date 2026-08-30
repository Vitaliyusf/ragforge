import { describe, expect, it } from 'vitest'
import {
  DOCUMENT_STATUSES,
  countByStatus,
  describeFailure,
  getDocumentStatus,
  getDocumentType,
  selectDocuments,
  summarizePipeline,
} from './documentModel'

const EMPTY_STAGE = {
  extraction: 'waiting',
  review: 'waiting',
  chunking: 'waiting',
  summary: 'waiting',
  embedding: 'waiting',
  semantic: 'waiting',
  vector: 'waiting',
  metadata: 'waiting',
}

function doc(overrides = {}) {
  return {
    file_id: 'file-1',
    filename: 'architecture.pdf',
    content_type: 'application/pdf',
    size: 2_400_000,
    status: 'complete',
    stage: { ...EMPTY_STAGE, ...(overrides.stage || {}) },
    updated_at: '2026-08-29T10:00:00Z',
    created_at: '2026-08-29T09:00:00Z',
    ...overrides,
  }
}

describe('getDocumentStatus', () => {
  it('maps the backend lifecycle onto the UI vocabulary', () => {
    expect(getDocumentStatus(doc({ status: 'complete' }))).toBe(DOCUMENT_STATUSES.READY)
    expect(getDocumentStatus(doc({ status: 'awaiting_review' }))).toBe(DOCUMENT_STATUSES.REVIEW)
    expect(getDocumentStatus(doc({ status: 'rejected' }))).toBe(DOCUMENT_STATUSES.REJECTED)
    expect(getDocumentStatus(doc({ status: 'error' }))).toBe(DOCUMENT_STATUSES.FAILED)
  })

  it('separates queued from processing by whether any stage has moved', () => {
    expect(getDocumentStatus(doc({ status: 'started' }))).toBe(DOCUMENT_STATUSES.QUEUED)
    expect(getDocumentStatus(doc({ status: 'started', stage: { extraction: 'running' } })))
      .toBe(DOCUMENT_STATUSES.PROCESSING)
  })
})

describe('summarizePipeline', () => {
  it('says "Indexed" once for a ready document instead of counting stages', () => {
    const ready = doc({
      status: 'complete',
      stage: Object.fromEntries(Object.keys(EMPTY_STAGE).map((key) => [key, 'done'])),
    })
    expect(summarizePipeline(ready)).toEqual({ state: 'done', label: 'Indexed', stageKey: 'vector' })
  })

  it('names the stage that is actually running', () => {
    const working = doc({
      status: 'processing',
      stage: { extraction: 'done', chunking: 'done', embedding: 'running' },
    })
    expect(summarizePipeline(working)).toMatchObject({ state: 'running', label: 'Embedding…' })
  })

  it('names the stage that failed', () => {
    const broken = doc({ status: 'processing', stage: { extraction: 'done', embedding: 'error' } })
    expect(summarizePipeline(broken)).toMatchObject({ state: 'failed', label: 'Embedding' })
  })
})

describe('describeFailure', () => {
  it('returns nothing for a healthy document', () => {
    expect(describeFailure(doc())).toBeNull()
  })

  it('takes the reason from a real audit event', () => {
    const broken = doc({ status: 'error', stage: { embedding: 'error' } })
    const failure = describeFailure(broken, [
      { event_type: 'stage_failed', to_status: 'error', reason: 'Embedding request timed out.' },
    ])
    expect(failure).toEqual({
      title: 'Embedding failed',
      reason: 'Embedding request timed out.',
      impact: 'This document is not searchable.',
    })
  })

  it('reports a missing reason as absent rather than inventing one', () => {
    const broken = doc({ status: 'error', stage: { embedding: 'error' } })
    expect(describeFailure(broken, []).reason).toBeNull()
  })
})

describe('getDocumentType', () => {
  it('prefers the extension and falls back to the MIME subtype', () => {
    expect(getDocumentType(doc())).toBe('PDF')
    expect(getDocumentType(doc({ filename: 'notes', content_type: 'text/plain' }))).toBe('PLAIN')
    expect(getDocumentType(doc({ filename: 'notes', content_type: 'application/octet-stream' })))
      .toBeNull()
  })
})

describe('selectDocuments', () => {
  const files = [
    doc({ file_id: 'a', filename: 'alpha.pdf', size: 100, updated_at: '2026-08-29T10:00:00Z' }),
    doc({
      file_id: 'b',
      filename: 'beta.docx',
      content_type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      size: 300,
      status: 'error',
      stage: { embedding: 'error' },
      updated_at: '2026-08-29T12:00:00Z',
    }),
    doc({
      file_id: 'c',
      filename: 'gamma.txt',
      content_type: 'text/plain',
      size: 200,
      status: 'started',
      updated_at: '2026-08-29T11:00:00Z',
    }),
  ]

  it('searches filenames and content types', () => {
    expect(selectDocuments(files, { query: 'beta' }).map((f) => f.file_id)).toEqual(['b'])
    expect(selectDocuments(files, { query: 'PDF' }).map((f) => f.file_id)).toEqual(['a'])
  })

  it('searches the file id, which is what a cross-screen link carries', () => {
    const withId = [
      doc({ file_id: 'file-7f2c', filename: 'delta.pdf', updated_at: '2026-08-29T10:00:00Z' }),
      ...files,
    ]
    expect(selectDocuments(withId, { query: 'file-7f2c' }).map((f) => f.file_id))
      .toEqual(['file-7f2c'])
  })

  it('filters by the UI status model', () => {
    expect(selectDocuments(files, { status: DOCUMENT_STATUSES.FAILED }).map((f) => f.file_id))
      .toEqual(['b'])
    expect(selectDocuments(files, { status: DOCUMENT_STATUSES.QUEUED }).map((f) => f.file_id))
      .toEqual(['c'])
  })

  it('sorts by updated, name, size and status', () => {
    expect(selectDocuments(files, { sort: 'updated' }).map((f) => f.file_id)).toEqual(['b', 'c', 'a'])
    expect(selectDocuments(files, { sort: 'updated', direction: 'asc' }).map((f) => f.file_id))
      .toEqual(['a', 'c', 'b'])
    expect(selectDocuments(files, { sort: 'name', direction: 'asc' }).map((f) => f.file_id))
      .toEqual(['a', 'b', 'c'])
    expect(selectDocuments(files, { sort: 'size' }).map((f) => f.file_id)).toEqual(['b', 'c', 'a'])
    // Descending status means "most urgent first".
    expect(selectDocuments(files, { sort: 'status' })[0].file_id).toBe('b')
  })

  it('does not mutate the input list', () => {
    const order = files.map((file) => file.file_id)
    selectDocuments(files, { sort: 'name' })
    expect(files.map((file) => file.file_id)).toEqual(order)
  })
})

describe('countByStatus', () => {
  it('counts each UI status and the total', () => {
    const counts = countByStatus([
      doc({ file_id: 'a' }),
      doc({ file_id: 'b', status: 'error' }),
      doc({ file_id: 'c', status: 'error' }),
    ])
    expect(counts.all).toBe(3)
    expect(counts[DOCUMENT_STATUSES.READY]).toBe(1)
    expect(counts[DOCUMENT_STATUSES.FAILED]).toBe(2)
  })
})
