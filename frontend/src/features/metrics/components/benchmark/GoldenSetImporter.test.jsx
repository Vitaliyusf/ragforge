import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { validateGoldenSet } = vi.hoisted(() => ({ validateGoldenSet: vi.fn() }))

vi.mock('../../services/metricsService', () => ({
  default: { validateGoldenSet },
}))

import GoldenSetImporter from './GoldenSetImporter'

const VALIDATION = {
  valid: true,
  total_items: 1,
  valid_items: 1,
  invalid_items: 0,
  errors: [],
}

const PREPARATION = {
  ready: 1,
  unresolved: 0,
  ambiguous: 0,
  unanswerable: 0,
  blocking: false,
}

function setup() {
  return render(
    <GoldenSetImporter
      open
      onOpenChange={vi.fn()}
      onSubmit={vi.fn().mockResolvedValue(true)}
    />
  )
}

async function validate(user) {
  await user.click(screen.getByRole('button', { name: 'Validate' }))
}

describe('GoldenSetImporter', () => {
  beforeEach(() => {
    validateGoldenSet.mockReset()
    validateGoldenSet.mockResolvedValue({ validation: VALIDATION, preparation: PREPARATION })
  })

  it('validates pasted JSON', async () => {
    const user = userEvent.setup()
    setup()
    const content = '[{"query":"Refund?","relevant_file_ids":["f-1"]}]'

    const textarea = screen.getByRole('textbox', { name: 'Golden Set content' })
    textarea.focus()
    await user.paste(content)
    await validate(user)

    expect(validateGoldenSet).toHaveBeenCalledWith({ content, format: 'json' })
  })

  it('reads and validates an uploaded JSON file', async () => {
    const user = userEvent.setup()
    setup()
    const content = '[{"query":"Refund?","relevant_file_ids":["f-1"]}]'
    const file = new File([content], 'golden.json', { type: 'application/json' })

    await user.upload(screen.getByLabelText('Upload JSON or JSONL'), file)
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Golden Set content' })).toHaveValue(content))
    await validate(user)

    expect(validateGoldenSet).toHaveBeenCalledWith({ content, format: 'json' })
  })

  it('detects JSONL from an uploaded .jsonl file', async () => {
    const user = userEvent.setup()
    setup()
    const content = '{"query":"One?","relevant_file_ids":["f-1"]}\n{"query":"Two?","relevant_file_ids":["f-2"]}'
    const file = new File([content], 'golden.jsonl', { type: 'application/x-ndjson' })

    await user.upload(screen.getByLabelText('Upload JSON or JSONL'), file)
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Pasted format' })).toHaveValue('jsonl'))
    await validate(user)

    expect(validateGoldenSet).toHaveBeenCalledWith({ content, format: 'jsonl' })
  })

  it('renders precise malformed-input errors returned by validation', async () => {
    validateGoldenSet.mockResolvedValue({
      validation: {
        valid: false,
        total_items: 0,
        valid_items: 0,
        invalid_items: 0,
        errors: [{ item_index: null, message: 'Malformed JSON at line 1, column 11' }],
      },
    })
    const user = userEvent.setup()
    setup()

    const textarea = screen.getByRole('textbox', { name: 'Golden Set content' })
    textarea.focus()
    await user.paste('[{"query":]')
    await validate(user)

    expect(await screen.findByText('Malformed JSON at line 1, column 11')).toBeInTheDocument()
  })

  it('renders a server validation failure', async () => {
    validateGoldenSet.mockRejectedValue(new Error('Validation service unavailable'))
    const user = userEvent.setup()
    setup()

    const textarea = screen.getByRole('textbox', { name: 'Golden Set content' })
    textarea.focus()
    await user.paste('{}')
    await validate(user)

    expect(await screen.findByText('Validation service unavailable')).toBeInTheDocument()
  })

  it('renders valid and invalid totals for a valid result', async () => {
    const user = userEvent.setup()
    setup()

    const textarea = screen.getByRole('textbox', { name: 'Golden Set content' })
    textarea.focus()
    await user.paste('{}')
    await validate(user)

    expect(await screen.findByText('Golden Set is valid')).toBeInTheDocument()
    expect(screen.getByText('1 ready · 0 unresolved · 0 ambiguous · 0 unanswerable')).toBeInTheDocument()
    expect(screen.getByText('1 valid · 0 invalid · 1 total')).toBeInTheDocument()
  })
})
