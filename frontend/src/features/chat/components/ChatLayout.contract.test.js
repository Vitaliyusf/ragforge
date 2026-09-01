import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const read = (name) => readFileSync(new URL(name, import.meta.url), 'utf8')

describe('desktop chat envelope', () => {
  it('widens the thread and composer without widening assistant prose', () => {
    const messageList = read('./MessageList.jsx')
    const chatInput = read('./ChatInput.jsx')
    const messageBubble = read('./MessageBubble.jsx')

    expect(messageList).toContain('max-w-[64rem]')
    expect(chatInput).toContain('max-w-[64rem]')
    expect(messageList).not.toContain('max-w-[46rem]')
    expect(chatInput).not.toContain('max-w-3xl')
    expect(messageBubble).toContain('max-w-[68ch]')
  })
})
