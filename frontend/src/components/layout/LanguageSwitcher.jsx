'use client'

import { useEffect, useRef, useState } from 'react'
import { Check, Languages } from 'lucide-react'
import { cn } from '@/lib/utils'
import { LOCALES, LOCALE_CODES, LOCALE_NAMES, useI18n } from '@/i18n'

/**
 * The one global interface-language control.
 *
 * No flags. A language is not a country — Hebrew is not the Israeli flag, and
 * English is not a choice between two of them — so the affordance is the
 * `Languages` glyph and each option is written in its own script.
 *
 * The menu is anchored to the *logical* end of the button rather than to the
 * right, because in Hebrew the whole utility cluster mirrors to the left edge
 * and a `right-0` panel would open off-screen.
 */
export default function LanguageSwitcher({ buttonClassName = '' }) {
  const { locale, setLocale, t } = useI18n()
  const [open, setOpen] = useState(false)
  const containerRef = useRef(null)

  // Dismissal listeners exist only while the menu is open, matching the
  // header's other popovers rather than leaving two document-level handlers
  // attached for the whole session.
  useEffect(() => {
    if (!open) return undefined
    const outsideHandler = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) setOpen(false)
    }
    const keyHandler = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', outsideHandler)
    document.addEventListener('keydown', keyHandler)
    return () => {
      document.removeEventListener('mousedown', outsideHandler)
      document.removeEventListener('keydown', keyHandler)
    }
  }, [open])

  const choose = (next) => {
    setLocale(next)
    setOpen(false)
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label={t('language.change')}
        title={t('language.short')}
        aria-expanded={open}
        aria-haspopup="menu"
        data-testid="language-switcher"
        className={cn(buttonClassName, open && 'bg-[var(--surface-hover)] text-[var(--fg)]')}
      >
        <Languages size={16} />
      </button>

      {open && (
        <div
          role="menu"
          aria-label={t('language.interface')}
          className="animate-dropdown-in absolute end-0 top-full z-[1000] mt-2 w-[13rem] overflow-hidden rounded-2xl border"
          style={{
            background: 'var(--surface-elevated)',
            borderColor: 'var(--border)',
            boxShadow: 'var(--shadow-xl)',
          }}
        >
          <div className="border-b px-4 py-2.5" style={{ borderColor: 'var(--border)' }}>
            <p className="text-xs font-medium text-[var(--fg-soft)]">{t('language.interface')}</p>
          </div>

          <div className="p-1.5">
            {LOCALES.map((option) => {
              const selected = option === locale
              return (
                <button
                  key={option}
                  type="button"
                  role="menuitemradio"
                  aria-checked={selected}
                  lang={option}
                  onClick={() => choose(option)}
                  data-locale={option}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-[13px] font-medium',
                    'transition-colors duration-150 focus-visible:outline-hidden focus-visible:ring-2',
                    'focus-visible:ring-[var(--ring)]',
                    selected
                      ? 'bg-[var(--primary-soft)] text-[var(--primary)]'
                      : 'text-[var(--fg-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--fg)]'
                  )}
                >
                  {/* The option's own name reads in its own direction; the
                      compact code stays LTR because EN/HE are identifiers. */}
                  <span className="flex-1 text-start">{LOCALE_NAMES[option]}</span>
                  <span
                    dir="ltr"
                    className="text-xs tabular-nums text-[var(--fg-soft)] [unicode-bidi:isolate]"
                  >
                    {LOCALE_CODES[option]}
                  </span>
                  <Check
                    size={14}
                    aria-hidden="true"
                    className={selected ? 'opacity-100' : 'opacity-0'}
                  />
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
