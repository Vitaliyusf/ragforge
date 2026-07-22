import { describe, expect, it } from 'vitest'
import { isExtendedMode, normalizeChatMode } from './chatMode'

describe('chatMode', () => {
  it('normalizes legacy quick mode to regular', () => {
    expect(normalizeChatMode('quick')).toBe('regular')
    expect(normalizeChatMode('regular')).toBe('regular')
    expect(normalizeChatMode('')).toBe('regular')
  })

  it('preserves extended mode and reports it correctly', () => {
    expect(normalizeChatMode('extended')).toBe('extended')
    expect(isExtendedMode('extended')).toBe(true)
    expect(isExtendedMode('regular')).toBe(false)
  })
})
