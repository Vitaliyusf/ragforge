import { describe, it, expect, beforeAll } from 'vitest'
import { compileGlobals } from './compileCss.js'

/**
 * Tailwind 4 compiles this app's design system from CSS rather than from a JS
 * config, and it fails quietly: a stylesheet that finds no source files still
 * builds, still ships, and simply contains no utilities. `next build` stays
 * green through all of it. These tests assert the integration contract that a
 * build cannot — that the semantic tokens reach real utilities — not Tailwind
 * itself.
 */

// The tokens under test are probed explicitly rather than relied on to appear
// in some component, so the contract holds even as call sites come and go.
const PROBE = [
  'flex', 'rounded-lg', 'rounded-2xl', 'rounded-control', 'rounded-surface',
  'bg-bg', 'bg-surface', 'bg-bg-tertiary', 'bg-primary', 'bg-danger', 'bg-error',
  'bg-status-live', 'text-fg', 'text-fg-soft', 'text-text-secondary',
  'text-text-muted', 'border-border', 'shadow-sm', 'shadow-xl', 'ring-2',
  'bg-surface/70', 'outline-hidden', 'scrollbar-thin', 'label-xs',
  'animate-blink', 'animate-fade-in', 'animate-shimmer', 'scrollbar-none',
  'scrollbar-thumb-border', 'scrollbar-track-transparent', 'bg-gradient-primary',
  'dark:bg-surface',
]

let css = ''
/** Compiled exactly as production does — no probe, so it reflects real usage. */
let productionCss = ''

beforeAll(async () => {
  ;[css, productionCss] = await Promise.all([compileGlobals({ probe: PROBE }), compileGlobals()])
}, 120_000)

const rule = (selector, source = css) => {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')
  const match = source.match(new RegExp('\\.' + escaped + '\\s*\\{([^}]*)'))
  return match ? match[1].replace(/\s+/g, ' ').trim() : null
}

describe('source detection', () => {
  // The highest-consequence failure mode of the v4 migration: globals.css lives
  // in src/styles/, so Tailwind's automatic detection alone finds no components
  // and compiles an empty stylesheet without any error.
  it('compiles utilities that only exist in app/ and src/ components', () => {
    expect(rule('flex', productionCss)).toContain('display: flex')
    expect(rule('bg-bg-tertiary', productionCss)).toBeTruthy()
    expect(rule('border-border', productionCss)).toBeTruthy()
  })

  it('does not compile classes that only test files mention', () => {
    // Tests are excluded from @source; otherwise assertions about removed
    // classes would compile those classes back into production CSS.
    expect(productionCss).not.toMatch(/\.bg-bg-tertiary\\\/70/)
  })
})

describe('semantic colour tokens reach utilities', () => {
  it.each([
    ['bg-bg', '--bg'],
    ['bg-surface', '--surface'],
    ['bg-bg-tertiary', '--surface'],
    ['text-fg', '--fg'],
    ['text-fg-soft', '--fg-soft'],
    ['text-text-secondary', '--fg-muted'],
    ['border-border', '--border'],
    ['bg-primary', '--primary'],
    ['bg-danger', '--danger'],
    ['bg-status-live', '--accent'],
  ])('%s resolves to var(%s)', (utility, variable) => {
    expect(rule(utility)).toContain(`var(${variable})`)
  })

  it('keeps compat aliases pointing at the same value as their modern name', () => {
    expect(rule('bg-bg-tertiary')).toEqual(rule('bg-surface'))
    expect(rule('text-text-muted')).toEqual(rule('text-fg-soft'))
    expect(rule('bg-error')).toEqual(rule('bg-danger'))
  })

  it('emits the raw var() spellings that JS reads directly', () => {
    // statusTone.js and the keyframe blocks consume these as plain var(), not
    // as utilities, so the @theme key alone is not enough: --color-status-live
    // is a different custom property than --status-live. Dropping the raw
    // spelling makes the live status tone resolve to nothing, with no build
    // error and no failing utility test.
    for (const name of ['--status-live', '--motion-fast', '--motion-normal', '--motion-easing']) {
      expect(css).toMatch(new RegExp(`${name}\\s*:`))
    }
  })

  it('resolves colours through var() so one .dark class repaints every utility', () => {
    // Without @theme inline the utility would inline a frozen hex here and dark
    // mode would stop working, with no build error to show for it.
    expect(rule('bg-surface')).not.toMatch(/#[0-9a-f]{3,8}/i)
    expect(css).toMatch(/\.dark\s*\{[^}]*--surface:/)
  })
})

describe('v3 to v4 breaking-change compatibility', () => {
  it('restores a semantic default border colour', () => {
    // v3 preflight defaulted to gray-200; v4 defaults to currentColor, which
    // would repaint ~170 bare `border` / `border-t` / `border-b` utilities.
    expect(css).toMatch(/\*,\s*::before,\s*::after,\s*::backdrop\s*\{[^}]*border-color:\s*var\(--border\)/)
  })

  it('restores a semantic default ring colour', () => {
    // Every ring in this app is an explicit width with no colour, so without
    // this the focus indicator falls back to currentColor.
    expect(css).toMatch(/\*\s*\{[^}]*--tw-ring-color:\s*var\(--ring\)/)
    expect(rule('ring-2')).toContain('--tw-ring-color')
  })

  it('keeps the tightened radius scale', () => {
    // The app overrides Tailwind's defaults: rounded-lg is 8px here, not 16px.
    expect(css).toMatch(/--radius-lg:\s*0\.5rem/)
    expect(css).toMatch(/--radius-2xl:\s*0\.75rem/)
    expect(rule('rounded-lg')).toContain('var(--radius-lg)')
    expect(rule('rounded-control')).toContain('var(--radius-control)')
    expect(rule('rounded-surface')).toContain('var(--radius-surface)')
  })

  it('keeps shadows on the app elevation scale rather than the v4 defaults', () => {
    // v4 renamed its shadow scale; this app defines its own, so shadow-sm must
    // still be the app's subtle elevation rather than Tailwind's.
    expect(rule('shadow-sm')).toContain('var(--shadow-sm)')
    expect(rule('shadow-xl')).toContain('var(--shadow-xl)')
  })

  it('emits working alpha modifiers', () => {
    // Under v3, an alpha modifier on a CSS-variable colour compiled to nothing
    // at all, so those call sites silently rendered no background. They work
    // now, which is why the accidental ones were removed from source.
    expect(rule('bg-surface\\/70')).toContain('color-mix')
  })

  it('carries no alpha modifiers on semantic colour tokens in production', () => {
    // Guards the migration decision: every one of these was a no-op under v3
    // and would have silently repainted on upgrade. A new one must be a
    // deliberate choice, made against the v4 rendering.
    const accidental = productionCss.match(
      /\.(bg|border|ring)-(bg-tertiary|bg-elevated|border|accent|primary)\\\/\d+/g
    )
    expect(accidental).toBeNull()
  })

  it('preserves the forced-colors focus fallback', () => {
    // v3's outline-none kept a transparent outline for forced-colors mode; v4
    // moved that behaviour to outline-hidden and made outline-none a plain
    // outline-style: none.
    expect(css).toMatch(/\.outline-hidden[\s\S]{0,200}forced-colors/)
  })
})

describe('custom utilities survive the @layer to @utility move', () => {
  it.each([
    'label-xs', 'animate-blink', 'animate-fade-in', 'animate-shimmer',
    'scrollbar-none', 'scrollbar-thumb-border', 'scrollbar-track-transparent',
    'bg-gradient-primary',
  ])('%s is emitted', (utility) => {
    expect(rule(utility)).toBeTruthy()
  })

  it('uses Tailwind 4 native scrollbar-width instead of a hand-rolled copy', () => {
    expect(rule('scrollbar-thin')).toContain('scrollbar-width: thin')
  })
})

describe('theme is driven by the .dark class, not the OS preference', () => {
  it('keeps the light surface hierarchy distinct and softly neutral', () => {
    for (const [token, value] of [
      ['bg', '#EEF2F7'],
      ['bg-subtle', '#E8EDF4'],
      ['surface', '#F8FAFC'],
      ['surface-elevated', '#FFFFFF'],
      ['surface-hover', '#F1F4F8'],
      ['surface-active', '#E7EBF2'],
      ['border', '#D6DDE8'],
      ['border-strong', '#C3CCD9'],
    ]) {
      expect(css).toMatch(new RegExp(`--${token}:\\s*${value}`, 'i'))
    }
  })

  it('emits the dark variant against .dark rather than prefers-color-scheme', () => {
    expect(css).toMatch(/\.dark\\:bg-surface:where\(\.dark/)
    expect(css).not.toMatch(/prefers-color-scheme/)
  })
})
