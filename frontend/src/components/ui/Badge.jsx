'use client'

import { cn } from '@/lib/utils'

/**
 * Semantic status badge system.
 * Variants: default | primary | success | warning | error | danger | info | accent | outline
 */

const variantStyles = {
  default: {
    background:  'var(--surface-hover)',
    color:       'var(--fg-muted)',
    borderColor: 'var(--border)',
  },
  primary: {
    background:  'var(--primary-soft)',
    color:       'var(--primary)',
    borderColor: 'transparent',
  },
  success: {
    background:  'var(--success-soft)',
    color:       'var(--success)',
    borderColor: 'transparent',
  },
  warning: {
    background:  'var(--warning-soft)',
    color:       'var(--warning)',
    borderColor: 'transparent',
  },
  error: {
    background:  'var(--danger-soft)',
    color:       'var(--danger)',
    borderColor: 'transparent',
  },
  danger: {
    background:  'var(--danger-soft)',
    color:       'var(--danger)',
    borderColor: 'transparent',
  },
  info: {
    background:  'var(--info-soft)',
    color:       'var(--info)',
    borderColor: 'transparent',
  },
  accent: {
    background:  'var(--accent-soft)',
    color:       'var(--accent)',
    borderColor: 'transparent',
  },
  outline: {
    background:  'transparent',
    color:       'var(--fg-muted)',
    borderColor: 'var(--border)',
  },
}

const sizeClasses = {
  xs: 'px-1.5 py-0.5 text-[10px] gap-1 rounded',
  sm: 'px-2 py-0.5 text-[11px] gap-1 rounded-md',
  md: 'px-2.5 py-1 text-xs gap-1.5 rounded-md',
}

export default function Badge({
  children,
  variant = 'default',
  size = 'sm',
  icon: Icon,
  pulse = false,
  dot = false,
  spin = false,
  className = '',
  style = {},
  ...props
}) {
  const vs = variantStyles[variant] || variantStyles.default
  const sc = sizeClasses[size] || sizeClasses.sm

  // Dot color fallback from fg
  const dotColor = vs.color

  return (
    <span
      className={cn(
        'inline-flex items-center font-medium border select-none whitespace-nowrap',
        sc,
        pulse && 'animate-pulse',
        className
      )}
      style={{ ...vs, ...style }}
      {...props}
    >
      {dot && (
        <span
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{ background: dotColor }}
        />
      )}
      {Icon && (
        <Icon
          size={size === 'xs' ? 10 : 12}
          className={cn('shrink-0', spin && 'animate-spin')}
        />
      )}
      {children}
    </span>
  )
}
