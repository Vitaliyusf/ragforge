import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it } from 'vitest'
import { renderWithProviders } from '@/test/render'
import { server } from '@/test/server'
import UploadTab from './UploadTab'

const API_BASE_URL = 'http://localhost:8000'

describe('UploadTab', () => {
  let ownFiles

  beforeEach(() => {
    ownFiles = []

    server.use(
      http.get(`${API_BASE_URL}/v1/files/mine`, () => HttpResponse.json({ files: ownFiles })),
      http.post(`${API_BASE_URL}/v1/files/upload`, () => {
        ownFiles = [
          {
            file_id: 'file-1',
            document_id: 'file-1',
            filename: 'policy.txt',
            content_type: 'text/plain',
            size: 128,
            status: 'awaiting_review',
            created_at: '2026-03-17T00:00:00Z',
          },
        ]
        return HttpResponse.json({ file_id: 'file-1', filename: 'policy.txt', status: 'accepted' })
      })
    )
  })

  it('lists the files the current user has uploaded', async () => {
    ownFiles = [
      {
        file_id: 'file-9',
        document_id: 'file-9',
        filename: 'handbook.pdf',
        content_type: 'application/pdf',
        size: 2048,
        status: 'complete',
        created_at: '2026-03-17T00:00:00Z',
      },
    ]

    renderWithProviders(<UploadTab />)

    expect(await screen.findByText('handbook.pdf')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()
  })

  it('shows a newly uploaded file without waiting for the next poll', async () => {
    const user = userEvent.setup()
    renderWithProviders(<UploadTab />)

    expect(await screen.findByText(/You have not uploaded any files yet/i)).toBeInTheDocument()

    const fileInput = screen.getByLabelText(/Choose a file/i)
    await user.upload(fileInput, new File(['file body'], 'policy.txt', { type: 'text/plain' }))
    await user.click(screen.getByRole('button', { name: /^Upload$/i }))

    expect(await screen.findByText('policy.txt')).toBeInTheDocument()
    expect(screen.getByText(/Under review/i)).toBeInTheDocument()
  })
})
