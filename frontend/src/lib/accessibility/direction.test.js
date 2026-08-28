import { describe, expect, it } from 'vitest'
import {
  bidiTextProps,
  containsHebrew,
  getTextDirection,
  isPrimarilyHebrew,
  ltrIsolateProps,
} from './direction'

const HEBREW = 'שלום עולם'
const MIXED = 'שלום gpt-4o-mini world and more english text here'

describe('direction detection', () => {
  it('detects Hebrew characters', () => {
    expect(containsHebrew(HEBREW)).toBe(true)
    expect(containsHebrew('hello')).toBe(false)
    expect(containsHebrew('')).toBe(false)
    expect(containsHebrew(null)).toBe(false)
  })

  it('treats a majority-Hebrew string as primarily Hebrew', () => {
    expect(isPrimarilyHebrew(HEBREW)).toBe(true)
    expect(isPrimarilyHebrew(MIXED)).toBe(false)
    expect(isPrimarilyHebrew('   ')).toBe(false)
  })

  it('resolves rtl, auto and ltr deterministically', () => {
    expect(getTextDirection(HEBREW)).toBe('rtl')
    expect(getTextDirection(MIXED)).toBe('auto')
    expect(getTextDirection('plain english')).toBe('ltr')
    expect(getTextDirection('')).toBe('ltr')
  })
})

describe('bidiTextProps', () => {
  it('pairs the direction with logical alignment', () => {
    expect(bidiTextProps(HEBREW)).toEqual({
      dir: 'rtl',
      direction: 'rtl',
      className: 'text-start',
    })
  })

  it('never emits a hard-coded side', () => {
    for (const text of [HEBREW, MIXED, 'english', '']) {
      const { className } = bidiTextProps(text)
      expect(className).not.toMatch(/text-(left|right)/)
    }
  })
})

describe('ltrIsolateProps', () => {
  it('forces ltr and isolates the run', () => {
    const props = ltrIsolateProps()
    expect(props.dir).toBe('ltr')
    expect(props.className).toContain('unicode-bidi:isolate')
  })
})
