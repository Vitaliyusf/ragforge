'use client'

import { ArrowUpRight } from 'lucide-react'
import Button from '@/components/ui/Button'
import { useWorkspaceNavigation } from '@/components/layout/NavigationContext'

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
  if (!link) return null

  return (
    <Button
      type="button"
      variant={variant}
      size={size}
      className={className}
      title={link.title}
      onClick={() => followDeepLink(link)}
      rightIcon={<ArrowUpRight size={12} />}
    >
      {children ?? link.label}
    </Button>
  )
}
