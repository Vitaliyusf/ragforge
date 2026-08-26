/**
 * Tests for the benchmark run surface.
 *
 * The point of this card is that the profile menu is the application's own
 * themed select — a native `<select>` renders an OS-white dropdown inside
 * the dark interface — and that an expensive profile is still confirmed
 * before it spends anything.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import RunBenchmarkCard from './RunBenchmarkCard'

function setup(props = {}) {
  const onStart = vi.fn()
  const view = render(
    <RunBenchmarkCard itemCount={30} ready busy={false} running={false} onStart={onStart} {...props} />
  )
  return { onStart, ...view }
}

async function pickProfile(user, name) {
  await user.click(screen.getByLabelText('Benchmark profile'))
  await user.click(await screen.findByRole('option', { name: new RegExp(name, 'i') }))
}

describe('RunBenchmarkCard profile selection', () => {
  it('uses the themed select rather than a native dropdown', () => {
    const { container } = setup()
    expect(container.querySelector('select')).toBeNull()
    expect(screen.getByLabelText('Benchmark profile')).toHaveAttribute('role', 'combobox')
  })

  it('shows each profile with its cost level and phases', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByLabelText('Benchmark profile'))

    const smoke = await screen.findByRole('option', { name: /Smoke Quality/i })
    expect(smoke).toHaveTextContent('Moderate')
    expect(smoke).toHaveTextContent('Regular E2E · 30 items')

    const quick = screen.getByRole('option', { name: /Quick Retrieval/i })
    expect(quick).toHaveTextContent('Fast')
    expect(quick).toHaveTextContent('Retrieval · 30 items')
  })

  it('starts the profile that was selected', async () => {
    const user = userEvent.setup()
    const { onStart } = setup()

    await pickProfile(user, 'Smoke Quality')
    await user.click(screen.getByRole('button', { name: /start benchmark/i }))
    await user.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: /start benchmark/i })
    )

    expect(onStart).toHaveBeenCalledWith('smoke_quality')
  })

  it('defaults to Full Quality and confirms before starting it', async () => {
    const user = userEvent.setup()
    const { onStart } = setup()

    await user.click(screen.getByRole('button', { name: /start benchmark/i }))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('Retrieval baseline + End-to-end')
    expect(dialog).not.toHaveTextContent(/expensive/i)

    await user.click(within(dialog).getByRole('button', { name: /start benchmark/i }))
    expect(onStart).toHaveBeenCalledWith('full_quality')
  })

  it('warns about an expensive profile and still requires confirmation', async () => {
    const user = userEvent.setup()
    const { onStart } = setup()

    await pickProfile(user, 'Full Diagnostic')
    expect(screen.getByText(/Expensive: runs Regular and Extended E2E/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /start benchmark/i }))
    expect(onStart).not.toHaveBeenCalled()

    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent(/This is an expensive profile/)
    await user.click(within(dialog).getByRole('button', { name: /start benchmark/i }))
    expect(onStart).toHaveBeenCalledWith('full_diagnostic')
  })

  it('never describes a profile as free and invents no duration', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByLabelText('Benchmark profile'))
    for (const option of screen.getAllByRole('option')) {
      expect(option.textContent).not.toMatch(/free/i)
      expect(option.textContent).not.toMatch(/\bmin(ute)?s?\b|\bETA\b/i)
    }
  })

  it('keeps the action blocked until a golden set is ready', () => {
    setup({ ready: false, itemCount: undefined })
    expect(screen.getByRole('button', { name: /start benchmark/i })).toBeDisabled()
    expect(screen.getByText(/import and validate a golden set/i)).toBeInTheDocument()
  })
})
