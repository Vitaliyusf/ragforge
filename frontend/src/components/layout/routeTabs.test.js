import { describe, expect, it } from 'vitest'
import { tabForPathname } from './routeTabs'

describe('tabForPathname', () => {
  it('sends /settings to the settings workspace', () => {
    expect(tabForPathname('/settings')).toBe('config')
  })

  it('sends the workspace roots to chat', () => {
    expect(tabForPathname('/')).toBe('chat')
    expect(tabForPathname('/dashboard')).toBe('chat')
    expect(tabForPathname('/chat/abc-123')).toBe('chat')
  })

  it('has no opinion about a path it does not own', () => {
    expect(tabForPathname('/something-else')).toBeNull()
    expect(tabForPathname(null)).toBeNull()
  })
})
