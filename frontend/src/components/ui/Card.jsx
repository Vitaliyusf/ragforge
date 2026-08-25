'use client'

import { cn } from '@/lib/utils'

/**
 * Surface-layered card system.
 * Variants: default | flat | elevated | interactive | ghost | glass
 */

const variantStyles = {
  default: {
    background: 'var(--surface)',
    border:     '1px solid var(--border)',
    boxShadow:  'var(--shadow-sm)',
  },
  flat: {
    background: 'var(--surface)',
  },
  elevated: {
    background: 'var(--surface-elevated)',
    border:     '1px solid var(--border)',
    boxShadow:  'var(--shadow-md)',
  },
  interactive: {
    background: 'var(--surface)',
    border:     '1px solid var(--border)',
    boxShadow:  'var(--shadow-sm)',
    cursor:     'pointer',
  },
  ghost: {
    background: 'transparent',
    border:     '1px solid var(--border)',
  },
  glass: {
    background:     'var(--glass)',
    border:         '1px solid var(--border)',
    backdropFilter: 'blur(18px)',
  },
  // backward-compat aliases
  hover: {
    background: 'var(--surface)',
    border:     '1px solid var(--border)',
    boxShadow:  'var(--shadow-sm)',
    cursor:     'pointer',
  },
}

const paddingMap = {
  none: '',
  xs:   'p-2.5',
  sm:   'p-4',
  md:   'p-5',
  lg:   'p-7',
}

export default function Card({
  children,
  variant = 'default',
  padding = 'md',
  className = '',
  style = {},
  onClick,
  ...props
}) {
  const baseStyle = variantStyles[variant] || variantStyles.default
  const isInteractive = ['interactive', 'hover'].includes(variant) || !!onClick

  return (
    <div
      className={cn(
        'overflow-hidden rounded-2xl',
        paddingMap[padding],
        isInteractive && 'transition-all duration-200 hover:border-[var(--border-strong)] hover:shadow-md',
        className
      )}
      style={{ ...baseStyle, ...style }}
      onClick={onClick}
      {...props}
    >
      {children}
    </div>
  )
}

/** Thin section divider inside a card */
export function CardSection({ children, className = '', ...props }) {
  return (
    <div
      className={cn('border-t pt-4 mt-4', className)}
      style={{ borderColor: 'var(--border)' }}
      {...props}
    >
      {children}
    </div>
  )
}

/** Card header row with title + optional action */
export function CardHeader({ title, description, action, className = '' }) {
  return (
    <div className={cn('flex items-start justify-between gap-3 mb-4', className)}>
      <div className="min-w-0">
        <h3 className="text-[15px] font-semibold truncate" style={{ color: 'var(--fg)' }}>
          {title}
        </h3>
        {description && (
          <p className="text-[13px] mt-0.5" style={{ color: 'var(--fg-soft)' }}>
            {description}
          </p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}
