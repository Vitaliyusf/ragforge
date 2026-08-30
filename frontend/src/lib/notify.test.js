import { describe, expect, it, vi, beforeEach } from 'vitest'
import { toast } from 'sonner'
import {
  NOTIFY_DURATION,
  describeError,
  notifyCritical,
  notifyError,
  notifySuccess,
} from './notify'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

beforeEach(() => vi.clearAllMocks())

describe('notifySuccess', () => {
  it('is short and carries no action — routine success interrupts nobody', () => {
    notifySuccess('Memory saved')
    const [message, options] = toast.success.mock.calls[0]
    expect(message).toBe('Memory saved')
    expect(options.duration).toBe(NOTIFY_DURATION.success)
    expect(options).not.toHaveProperty('action')
  })
})

describe('notifyError', () => {
  it('offers the recovery action when the caller can retry', () => {
    const onRetry = vi.fn()
    notifyError('Failed to load models', { error: new Error('502'), onRetry })
    const [, options] = toast.error.mock.calls[0]
    expect(options.description).toBe('502')
    expect(options.duration).toBe(NOTIFY_DURATION.error)
    options.action.onClick()
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('omits the action rather than offering a dead button', () => {
    notifyError('Decision failed', { error: new Error('nope') })
    expect(toast.error.mock.calls[0][1].action).toBeUndefined()
  })

  it('auto-dismisses — an ordinary error is not a blocker', () => {
    notifyError('Upload failed')
    expect(toast.error.mock.calls[0][1].duration).toBeLessThan(Infinity)
  })
})

describe('notifyCritical', () => {
  it('stays until the person dismisses it', () => {
    notifyCritical('Configuration unavailable')
    const [, options] = toast.error.mock.calls[0]
    expect(options.duration).toBe(Infinity)
    expect(options.dismissible).toBe(true)
  })
})

describe('describeError', () => {
  it('falls back rather than showing an empty line', () => {
    expect(describeError(new Error('   '))).toBe('Please try again.')
    expect(describeError(undefined)).toBe('Please try again.')
    expect(describeError('plain string')).toBe('plain string')
  })
})
