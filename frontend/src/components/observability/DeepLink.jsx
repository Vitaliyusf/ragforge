'use client'

import { ArrowUpRight } from 'lucide-react'
import Button from '@/components/ui/Button'
import { useWorkspaceNavigation } from '@/components/layout/NavigationContext'
import { useI18n } from '@/i18n'

/**
 * The button that follows one cross-screen link.
 *
 * It knows nothing about the store, the router or the tab state — the shell
 * owns all three and hands down one executor. That is what lets a metrics
 * table offer a jump without a provider stack above it.
 *
 * Renders nothing for a null link. A builder returns null precisely when
 * there is no identifier worth jumping on, and an offer that lands somewhere
 * unfiltered is worse than no offer.
 */
export default function DeepLink({
  link,
  children,
  variant = 'ghost',
  size = 'xs',
  className = '',
}) {
  const { followDeepLink } = useWorkspaceNavigation()
  const { t } = useI18n()
  if (!link) return null

  // The builder is pure and carries English text plus the keys that name it.
  // Resolving here is what lets one descriptor serve both languages — and the
  // caveat is nested, so it is resolved before the outer sentence.
  const vars = link.titleVars?.caveatKey
    ? { ...link.titleVars, caveat: t(link.titleVars.caveatKey) }
    : link.titleVars
  const title = link.titleKey ? t(link.titleKey, vars) : link.title
  const label = link.labelKey ? t(link.labelKey, link.labelVars) : link.label

  return (
    <Button
      type="button"
      variant={variant}
      size={size}
      className={className}
      title={title}
      onClick={() => followDeepLink(link)}
      rightIcon={<ArrowUpRight size={12} />}
    >
      {children ?? label}
    </Button>
  )
}
