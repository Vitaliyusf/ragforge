import { describe, expect, it } from 'vitest'
import { buildInitialState, filesReducer } from './filesReducer'

function file(overrides = {}) {
  return {
    file_id: 'file-1',
    document_id: 'file-1',
    filename: 'a.pdf',
    status: 'processing',
    stage: { extraction: 'done', embedding: 'running' },
    ...overrides,
  }
}

describe('LOAD_SUCCESS row identity', () => {
  it('reuses the previous object for a document that did not change', () => {
    const first = filesReducer(buildInitialState([]), {
      type: 'LOAD_SUCCESS',
      files: [file(), file({ file_id: 'file-2', filename: 'b.pdf' })],
    })

    const second = filesReducer(first, {
      type: 'LOAD_SUCCESS',
      files: [file(), file({ file_id: 'file-2', filename: 'b.pdf' })],
    })

    // Same values arriving from a fresh poll must not invalidate memoised rows.
    expect(second.files[0]).toBe(first.files[0])
    expect(second.files[1]).toBe(first.files[1])
  })

  it('replaces only the document whose state moved', () => {
    const first = filesReducer(buildInitialState([]), {
      type: 'LOAD_SUCCESS',
      files: [file(), file({ file_id: 'file-2', filename: 'b.pdf' })],
    })

    const second = filesReducer(first, {
      type: 'LOAD_SUCCESS',
      files: [
        file({ status: 'complete', stage: { extraction: 'done', embedding: 'done' } }),
        file({ file_id: 'file-2', filename: 'b.pdf' }),
      ],
    })

    expect(second.files[0]).not.toBe(first.files[0])
    expect(second.files[0].status).toBe('complete')
    expect(second.files[1]).toBe(first.files[1])
  })
})
