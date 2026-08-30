import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'

/**
 * `outline-hidden` removes the browser's own focus ring. That is fine — the
 * app paints its own — but only if the same element actually paints one.
 * Suppressing the outline and forgetting the ring leaves a keyboard user with
 * no idea what is focused, and it is invisible to anyone testing with a mouse,
 * so it is caught here rather than in review.
 *
 * Each entry below is an element whose focus ring lives on an ancestor, with
 * the ancestor's marker named. Any other bare `outline-hidden` is a defect.
 */
const RING_ON_AN_ANCESTOR = {
  // The composer wraps the textarea and the send button in one bordered shell
  // that lights up via `focus-within`, so the textarea has no ring of its own.
  'src/features/chat/components/ChatInput.jsx': ['focus-within:ring-2'],
}

/**
 * A focus indicator: any focus-state utility that paints something (a ring, an
 * offset, a border, a skip link leaving `sr-only`) plus Radix's keyboard
 * highlight. `focus:outline-hidden` is the suppression itself, so it is
 * explicitly not an indicator.
 */
const FOCUS_INDICATOR = /(?:focus|focus-visible|focus-within):(?!outline-)|data-highlighted/

/**
 * Every directory holding component source. There is no top-level
 * `frontend/components`: jsconfig maps `@/*` to `./src/*`, so `@/components`
 * is `src/components` and the guard already reaches it through `src`. Listing
 * it here scanned nothing on a machine that happened to have a stale empty
 * directory and threw ENOENT on a clean checkout.
 */
const ROOTS = ['src', 'app']
const REPO = path.resolve(__dirname, '../../..')

function sourceFiles() {
  const found = []
  const walk = (dir) => {
    for (const entry of readdirSync(dir)) {
      const full = path.join(dir, entry)
      if (statSync(full).isDirectory()) walk(full)
      else if (/\.jsx?$/.test(entry) && !entry.includes('.test.')) found.push(full)
    }
  }
  for (const root of ROOTS) {
    const full = path.join(REPO, root)
    // A root that has moved must fail by name. Skipping it silently would let
    // this guard shrink to nothing while still reporting green.
    if (!existsSync(full)) throw new Error(`focus-visibility guard: missing source root '${root}'`)
    walk(full)
  }
  return found
}

/**
 * Blank out comments in place, so prose *about* `outline-hidden` is not read
 * as code while every remaining offset still points at its original line.
 */
function withoutComments(text) {
  const blank = (match) => match.replace(/[^\r\n]/g, ' ')
  return text
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/(^|[^:])(\/\/.*)/g, (whole, lead, comment) => lead + blank(comment))
}

/**
 * The scopes a ring for this element could legitimately live in: the string
 * literal holding the utility (a shared `FOCUS_RING` constant, a cva slot),
 * and the `className={...}` expression that composes it.
 */
function scopesAround(text, at) {
  const scopes = []

  const quote = Math.max(
    text.lastIndexOf("'", at), text.lastIndexOf('"', at), text.lastIndexOf('`', at)
  )
  if (quote !== -1) {
    const end = text.indexOf(text[quote], at)
    scopes.push(text.slice(quote, end === -1 ? text.length : end + 1))
  }

  const start = text.lastIndexOf('className=', at)
  if (start !== -1 && text[start + 'className='.length] === '{') {
    let depth = 0
    for (let i = start + 'className='.length; i < text.length; i += 1) {
      if (text[i] === '{') depth += 1
      else if (text[i] === '}' && (depth -= 1) === 0) {
        if (i > at) scopes.push(text.slice(start, i + 1))
        break
      }
    }
  }

  return scopes
}

describe('focus visibility', () => {
  it('never suppresses the outline without painting a ring in its place', () => {
    const offenders = []
    for (const file of sourceFiles()) {
      const relative = path.relative(REPO, file).split(path.sep).join('/')
      const text = withoutComments(readFileSync(file, 'utf8'))
      const allowed = RING_ON_AN_ANCESTOR[relative] || []
      for (let at = text.indexOf('outline-hidden'); at !== -1; at = text.indexOf('outline-hidden', at + 1)) {
        const covered =
          scopesAround(text, at).some((scope) => FOCUS_INDICATOR.test(scope)) ||
          allowed.some((token) => text.includes(token))
        if (!covered) {
          offenders.push(`${relative}:${text.slice(0, at).split('\n').length}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })

  it('actually notices a suppression with nothing in its place', () => {
    const sample = '<button className="rounded-lg p-2 outline-hidden">x</button>'
    expect(scopesAround(sample, sample.indexOf('outline-hidden'))
      .some((scope) => FOCUS_INDICATOR.test(scope))).toBe(false)
  })
})
