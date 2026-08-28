const path = require('path')
const fs = require('fs')

const CSS_PATH = path.join(__dirname, 'globals.css')

/**
 * Compile globals.css exactly the way the production PostCSS pipeline does.
 *
 * Tailwind 4 resolves `@source` relative to the stylesheet and silently emits
 * zero utilities when it cannot find them, so the only trustworthy check on
 * the design system is the compiled output. Tests use this; nothing ships it.
 *
 * `probe` force-generates the named utilities via `@source inline(...)`.
 * Tailwind only emits utilities it finds in source, so without this a test for
 * "does --danger reach bg-danger" would really be testing "does some component
 * happen to use bg-danger today". The probe separates the two.
 */
async function compileGlobals({ probe = [] } = {}) {
  const postcss = require('postcss')
  const tailwind = require('@tailwindcss/postcss')
  let css = fs.readFileSync(CSS_PATH, 'utf8')
  if (probe.length) {
    css += `\n@source inline("${probe.join(' ')}");\n`
  }
  const result = await postcss([tailwind()]).process(css, { from: CSS_PATH })
  return result.css
}

module.exports = { compileGlobals, CSS_PATH }
