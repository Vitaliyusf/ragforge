import { describe, expect, it } from 'vitest'

import { HISTORY_MESSAGE_LIMIT } from './chatConstants'
import { formatHistoryForPrompt } from './chatHelpers'

describe('formatHistoryForPrompt', () => {
  it('returns an empty string when there is no history', () => {
    expect(formatHistoryForPrompt([])).toBe('')
    expect(formatHistoryForPrompt(undefined)).toBe('')
  })

  it('formats sender/text pairs and drops blank messages', () => {
    const history = [
      { sender: 'You', text: 'hello' },
      { sender: 'Assistant', text: '   ' },
      { sender: 'Assistant', text: 'hi there' },
    ]
    expect(formatHistoryForPrompt(history)).toBe('[You]: hello\n[Assistant]: hi there')
  })

  it('keeps only the most recent HISTORY_MESSAGE_LIMIT messages', () => {
    const history = Array.from({ length: HISTORY_MESSAGE_LIMIT + 5 }, (_, index) => ({
      sender: 'You',
      text: `message-${index}`,
    }))
    const lines = formatHistoryForPrompt(history).split('\n')
    expect(lines).toHaveLength(HISTORY_MESSAGE_LIMIT)
    expect(lines[0]).toBe('[You]: message-5')
  })
})
