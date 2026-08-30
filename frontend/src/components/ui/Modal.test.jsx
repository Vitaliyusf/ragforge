import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Modal, { ConfirmModal } from './Modal'

describe('Modal', () => {
  it('links its description so a screen reader reads it with the title', () => {
    render(
      <Modal open onOpenChange={() => {}} title="Delete this document?" description="It goes away.">
        <p>body</p>
      </Modal>
    )
    const dialog = screen.getByRole('dialog')
    const describedBy = dialog.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()
    expect(document.getElementById(describedBy)).toHaveTextContent('It goes away.')
  })

  it('drops aria-describedby when there is no description to point at', () => {
    render(
      <Modal open onOpenChange={() => {}} title="Import a golden set">
        <form />
      </Modal>
    )
    expect(screen.getByRole('dialog')).not.toHaveAttribute('aria-describedby')
  })
})

describe('ConfirmModal', () => {
  it('describes the impact through the dialog description', () => {
    render(
      <ConfirmModal
        open
        onOpenChange={() => {}}
        title="Delete chat?"
        description="Messages and chat memory are removed."
        variant="danger"
      />
    )
    const describedBy = screen.getByRole('dialog').getAttribute('aria-describedby')
    expect(document.getElementById(describedBy)).toHaveTextContent(
      'Messages and chat memory are removed.'
    )
  })

  it('keeps a focus indicator on both controls — one of them is destructive', () => {
    render(
      <ConfirmModal open onOpenChange={() => {}} title="Delete chat?" variant="danger"
        confirmLabel="Delete" />
    )
    for (const name of ['Delete', 'Cancel']) {
      expect(screen.getByRole('button', { name }).className).toMatch(/focus-visible:ring-2/)
    }
  })

  it('confirms and closes, and is reachable by keyboard', async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    const onOpenChange = vi.fn()
    render(
      <ConfirmModal open onOpenChange={onOpenChange} title="Delete chat?" confirmLabel="Delete"
        onConfirm={onConfirm} variant="danger" />
    )
    const confirm = screen.getByRole('button', { name: 'Delete' })
    confirm.focus()
    await user.keyboard('{Enter}')
    expect(onConfirm).toHaveBeenCalledOnce()
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('locks both the close and the confirm while the action is in flight', () => {
    render(
      <ConfirmModal open onOpenChange={() => {}} title="Delete chat?" confirmLabel="Delete" loading />
    )
    expect(screen.queryByRole('button', { name: 'Close' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Working…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled()
  })
})
