import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import FilesTab from './FilesTab'

const API_BASE_URL = 'http://localhost:8000'

function createFile(overrides = {}) {
  return {
    file_id: 'file-1',
    document_id: 'file-1',
    filename: 'policy.txt',
    content_type: 'text/plain',
    size: 128,
    status: 'awaiting_review',
    review_status: 'pending',
    latest_review_case_id: 'review-1',
    ...overrides,
  }
}

describe('FilesTab', () => {
  let files
  let capturedDecision
  let auditRequests

  beforeEach(() => {
    files = []
    capturedDecision = null
    auditRequests = []

    server.use(
      http.get(`${API_BASE_URL}/v1/files`, () => {
        return HttpResponse.json({ files })
      }),
      http.post(`${API_BASE_URL}/v1/files/upload`, () => {
        const response = {
          file_id: 'file-1',
          document_id: 'doc-1',
          current_task_id: 'task-1',
          filename: 'policy.txt',
          status: 'awaiting_review',
          message: 'queued',
        }

        files = [
          createFile({
            filename: response.filename,
          }),
        ]

        return HttpResponse.json(response)
      }),
      http.get(`${API_BASE_URL}/v1/files/:fileId/review-case`, ({ params }) => {
        return HttpResponse.json({
          file_id: params.fileId,
          document_id: params.fileId,
          review_case_id: 'review-1',
          status: 'open',
          decision_status: 'pending',
          problem_description: 'Sensitive identifier detected',
          problematic_text: 'SSN: 123-45-6789',
          why_problematic: 'Contains personal data that must be redacted.',
          issue_categories: [{ category: 'pii' }],
          allowed_actions: ['delete_file', 'remove_problematic_text', 'accept_as_is'],
          redaction_patch_map: [
            {
              patch_id: 'patch-1',
              action: 'replace',
              start: 5,
              end: 16,
              replacement: '[REDACTED]',
              reason: 'Remove SSN',
            },
          ],
          extracted_text_hash: 'hash-1',
          opened_at: '2026-03-17T00:00:00Z',
        })
      }),
      http.post(`${API_BASE_URL}/v1/files/:fileId/review-decision`, async ({ request }) => {
        capturedDecision = await request.json()
        files = [
          createFile({
            status: 'processing',
            review_status: 'approved_sanitized',
          }),
        ]
        return HttpResponse.json({
          file_status: 'processing',
          decision_id: 'decision-1',
        })
      }),
      http.get(`${API_BASE_URL}/v1/files/:fileId/audit-trail`, ({ request }) => {
        const url = new URL(request.url)
        const cursor = url.searchParams.get('cursor')
        auditRequests.push(cursor)

        if (cursor === 'cursor-2') {
          return HttpResponse.json({
            events: [
              {
                event_id: 'event-2',
                file_id: 'file-1',
                document_id: 'file-1',
                task_id: 'task-1',
                event_type: 'review_decision_submitted',
                from_status: 'awaiting_review',
                to_status: 'processing',
                actor: { actor_id: 'reviewer-7', display_name: 'reviewer-7' },
                reason: 'manual review',
                details: { action: 'remove_problematic_text' },
                file_ref: { file_id: 'file-1' },
                review_case_id: 'review-1',
                decision_id: 'decision-1',
                created_at: '2026-03-17T00:05:00Z',
              },
            ],
            next_cursor: null,
          })
        }

        return HttpResponse.json({
          events: [
            {
              event_id: 'event-1',
              file_id: 'file-1',
              document_id: 'file-1',
              task_id: 'task-1',
              event_type: 'file_uploaded',
              from_status: null,
              to_status: 'awaiting_review',
              actor: { actor_id: 'gateway', display_name: 'gateway' },
              reason: 'upload',
              details: { filename: 'policy.txt' },
              file_ref: { file_id: 'file-1' },
              review_case_id: 'review-1',
              decision_id: null,
              created_at: '2026-03-17T00:00:00Z',
            },
          ],
          next_cursor: 'cursor-2',
        })
      }),
      http.delete(`${API_BASE_URL}/v1/files/:fileId`, () => {
        files = []
        return HttpResponse.json({ deleted: true })
      })
    )
  })

  it('uploads files through the gateway and shows the immediate file id and status', async () => {
    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)

    expect(await screen.findByText(/No files uploaded yet/i)).toBeInTheDocument()

    const fileInput = screen.getByRole('button', { name: /Upload files/i }).querySelector('input[type="file"]')
    expect(fileInput).toBeTruthy()

    await user.upload(fileInput, new File(['file body'], 'policy.txt', { type: 'text/plain' }))

    expect((await screen.findAllByText(/file-1/i)).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/awaiting review/i).length).toBeGreaterThan(0)
    expect(await screen.findByRole('button', { name: /Review file/i })).toBeInTheDocument()
  })

  it('loads a review case and submits a compliant review decision payload', async () => {
    files = [createFile()]

    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)

    expect(await screen.findByText('policy.txt')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Review file/i }))

    expect(await screen.findByText(/Sensitive identifier detected/i)).toBeInTheDocument()
    expect(screen.getByText(/Extracted text hash/i)).toBeInTheDocument()
    expect(screen.getByText(/hash-1/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Remove problematic text/i }))
    await user.type(screen.getByPlaceholderText(/Optional decision note/i), 'Remove the secret')
    await user.click(screen.getByRole('button', { name: /Submit decision/i }))

    await waitFor(() => {
      expect(capturedDecision).not.toBeNull()
    })

    expect(capturedDecision).toMatchObject({
      review_case_id: 'review-1',
      decision: 'remove_problematic_text',
      based_on_text_hash: 'hash-1',
      notes: 'Remove the secret',
      metadata: {
        source: 'frontend_admin_review',
      },
    })
    expect(capturedDecision).not.toHaveProperty('reviewer')
    expect(capturedDecision.patch_map).toEqual([
      expect.objectContaining({
        patch_id: 'patch-1',
        replacement: '[REDACTED]',
      }),
    ])

    await waitFor(() => {
      expect(screen.queryByText(/Review File:/i)).not.toBeInTheDocument()
    })

    expect(await screen.findByText(/resumed/i)).toBeInTheDocument()
  })

  it('fetches audit trail pages and renders the timeline', async () => {
    files = [createFile({ status: 'complete', review_status: 'approved_as_is' })]

    const user = userEvent.setup()
    renderWithProviders(<FilesTab />)

    expect(await screen.findByText('policy.txt')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /View Audit Trail/i }))

    expect(await screen.findByText('file_uploaded')).toBeInTheDocument()
    expect(screen.getByText(/Event ID/i)).toBeInTheDocument()
    expect(screen.getAllByText(/task-1/i).length).toBeGreaterThan(0)

    await user.click(screen.getByRole('button', { name: /Load more/i }))

    expect(await screen.findByText('review_decision_submitted')).toBeInTheDocument()
    expect(auditRequests).toContain('cursor-2')
  })
})
