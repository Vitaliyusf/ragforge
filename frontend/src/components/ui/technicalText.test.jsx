/**
 * Technical text under a Hebrew interface.
 *
 * A model id, an email address, a hash, a log line and a JSON payload all
 * mean exactly one thing and read in exactly one direction. Inside an RTL
 * run an unisolated identifier has its punctuation reordered — `gpt-4o-mini.`
 * renders as `.gpt-4o-mini` — and that is not cosmetic: it is a value the
 * reader may be about to copy into a terminal or a bug report.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import TechnicalText from './TechnicalText'
import { CodeBlock } from './DataDisplay'
import { I18nProvider } from '@/i18n'
import { ltrIsolateProps, techLtrProps } from '@/lib/accessibility/direction'

const inHebrew = (ui) => render(<I18nProvider initialLocale="he">{ui}</I18nProvider>)

describe('direction helpers', () => {
  it('isolates an inline identifier so it cannot reorder the text around it', () => {
    const props = ltrIsolateProps()
    expect(props.dir).toBe('ltr')
    expect(props.className).toContain('unicode-bidi:isolate')
  })

  it('gives a block of technical text its own direction and left alignment', () => {
    const props = techLtrProps()
    expect(props.dir).toBe('ltr')
    // `text-left`, not `text-start`: a log viewport must not follow the shell.
    expect(props.className).toContain('text-left')
    expect(props.className).toContain('unicode-bidi:isolate')
  })
})

describe('TechnicalText', () => {
  it('keeps a model id left-to-right inside a Hebrew shell', () => {
    inHebrew(<TechnicalText>Qwen/Qwen2.5-7B-Instruct</TechnicalText>)
    const element = screen.getByText('Qwen/Qwen2.5-7B-Instruct')
    expect(element).toHaveAttribute('dir', 'ltr')
    expect(element.className).toContain('unicode-bidi:isolate')
  })

  it('keeps an email address left-to-right', () => {
    inHebrew(<TechnicalText>operator@example.com</TechnicalText>)
    expect(screen.getByText('operator@example.com')).toHaveAttribute('dir', 'ltr')
  })

  it('keeps a hash left-to-right', () => {
    inHebrew(<TechnicalText>9f2c1a4e7b30</TechnicalText>)
    expect(screen.getByText('9f2c1a4e7b30')).toHaveAttribute('dir', 'ltr')
  })

  it('gives a block-level payload its own alignment, not the shells', () => {
    inHebrew(
      <TechnicalText as="pre" block>
        {'{"trace_id": "abc-123"}'}
      </TechnicalText>
    )
    const block = screen.getByText('{"trace_id": "abc-123"}')
    expect(block.tagName).toBe('PRE')
    expect(block).toHaveAttribute('dir', 'ltr')
    expect(block.className).toContain('text-left')
  })
})

describe('CodeBlock', () => {
  it('renders JSON left-to-right and left-aligned in a Hebrew interface', () => {
    inHebrew(<CodeBlock content={{ request_id: 'req-77' }} />)
    const block = screen.getByText(/request_id/)
    expect(block).toHaveAttribute('dir', 'ltr')
    expect(block.className).toContain('text-left')
    expect(block.className).toContain('unicode-bidi:isolate')
  })

  it('says the payload is unavailable in the readers language', () => {
    inHebrew(<CodeBlock content={null} />)
    expect(screen.getByText('לא זמין')).toBeInTheDocument()
  })
})
