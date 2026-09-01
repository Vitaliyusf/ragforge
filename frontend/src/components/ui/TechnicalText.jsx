'use client'

import { cn } from '@/lib/utils'
import { ltrIsolateProps, techLtrProps } from '@/lib/accessibility/direction'

/**
 * Text the bidi algorithm must not touch.
 *
 * Model ids, UUIDs, request and trace ids, hashes, URLs, email addresses, IP
 * addresses and ports, JSON, log lines and Kafka topics all mean exactly one
 * thing and read in exactly one direction. Inside a Hebrew paragraph an
 * unisolated identifier has its punctuation reordered — `gpt-4o-mini.` renders
 * as `.gpt-4o-mini` — which is not a cosmetic problem: it is a value a reader
 * may be about to copy into a terminal.
 *
 * `block` switches from the inline isolate to the block treatment, for a log
 * viewport or a preformatted payload that must also keep left alignment and
 * its own scrolling.
 */
export default function TechnicalText({
  children,
  as: Tag = 'span',
  block = false,
  className = '',
  ...rest
}) {
  const props = block ? techLtrProps() : ltrIsolateProps()
  return (
    <Tag {...rest} dir={props.dir} className={cn(props.className, className)}>
      {children}
    </Tag>
  )
}
