'use client'

import { Loader2 } from 'lucide-react'
import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  [
    'inline-flex items-center justify-center font-medium select-none',
    'transition-colors duration-150',
    'focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg)]',
    'disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none',
  ].join(' '),
  {
    variants: {
      // Flat fills, shifted on hover. No gradient, no lift, no glow — a button
      // should read as a surface you press, not as an object floating away.
      variant: {
        primary:
          'bg-[var(--primary)] text-[var(--primary-fg)] shadow-sm hover:bg-[var(--primary-hover)]',
        secondary:
          'border border-[var(--border)] bg-[var(--secondary)] text-[var(--fg-muted)] hover:bg-[var(--secondary-hover)] hover:text-[var(--fg)]',
        ghost:
          'border border-transparent bg-transparent text-[var(--fg-muted)] hover:bg-[var(--surface-hover)] hover:text-[var(--fg)]',
        outline:
          'border border-[var(--primary)] bg-transparent text-[var(--primary)] hover:bg-[var(--primary-soft)]',
        danger:
          'bg-[var(--danger)] text-white shadow-sm hover:brightness-110',
        'danger-ghost':
          'border border-transparent bg-transparent text-[var(--danger)] hover:bg-[var(--danger-soft)]',
      },
      size: {
        xs:   'min-h-7 px-2.5 py-1 text-xs gap-1 rounded-lg',
        sm:   'min-h-8 px-3 py-1.5 text-[13px] gap-1.5 rounded-lg',
        md:   'min-h-10 px-4 py-2 text-[15px] gap-2 rounded-xl',
        lg:   'min-h-11 px-6 py-2.5 text-[15px] gap-2.5 rounded-xl',
        icon: 'h-9 w-9 rounded-xl',
        'icon-sm': 'h-7 w-7 rounded-lg',
      },
    },
    defaultVariants: {
      variant: 'primary',
      size: 'md',
    },
  }
)

export default function Button({
  children,
  onClick,
  disabled = false,
  variant = 'primary',
  size = 'md',
  type = 'button',
  loading = false,
  leftIcon,
  rightIcon,
  className = '',
  style = {},
  ...props
}) {
  const iconSize = size === 'icon' || size === 'icon-sm' ? 16
    : size === 'xs' || size === 'sm' ? 13
    : 15

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={cn(buttonVariants({ variant, size }), className)}
      style={style}
      {...props}
    >
      {loading ? (
        <Loader2 size={iconSize} className="animate-spin shrink-0" />
      ) : leftIcon ? (
        <span className="shrink-0">{leftIcon}</span>
      ) : null}
      {children}
      {!loading && rightIcon ? <span className="shrink-0">{rightIcon}</span> : null}
    </button>
  )
}
