'use client'

import { Loader2 } from 'lucide-react'
import { cva } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  [
    'inline-flex items-center justify-center font-medium select-none',
    'transition-all duration-200',
    'focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg)]',
    'disabled:opacity-50 disabled:cursor-not-allowed disabled:pointer-events-none',
    'active:scale-[0.985]',
  ].join(' '),
  {
    variants: {
      variant: {
        primary: [
          'text-white shadow-sm',
          'hover:-translate-y-px hover:shadow-glow hover:brightness-105',
        ].join(' '),
        secondary: [
          'border transition-colors',
        ].join(' '),
        ghost: [
          'border-transparent',
        ].join(' '),
        outline: [
          'border bg-transparent',
        ].join(' '),
        danger: [
          'bg-[var(--danger)] text-white shadow-sm hover:brightness-110',
        ].join(' '),
        'danger-ghost': [
          'bg-transparent border-transparent text-[var(--danger)]',
          'hover:bg-[var(--danger-soft)]',
        ].join(' '),
      },
      size: {
        xs:   'min-h-7 px-2.5 py-1 text-[11px] gap-1 rounded-lg',
        sm:   'min-h-8 px-3 py-1.5 text-xs gap-1.5 rounded-lg',
        md:   'min-h-10 px-4 py-2 text-sm gap-2 rounded-xl',
        lg:   'min-h-11 px-6 py-2.5 text-sm gap-2.5 rounded-xl',
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
  // Apply CSS-var styles that CVA can't handle
  const variantStyle = (() => {
    switch (variant) {
      case 'primary':
        return { background: 'var(--gradient-primary)', color: 'var(--primary-fg)' }
      case 'secondary':
        return {
          background:   'var(--secondary)',
          color:        'var(--fg-muted)',
          borderColor:  'var(--border)',
        }
      case 'ghost':
        return { background: 'transparent', color: 'var(--fg-muted)' }
      case 'outline':
        return {
          background:  'transparent',
          color:       'var(--primary)',
          borderColor: 'var(--primary)',
        }
      case 'danger':
        return {}
      case 'danger-ghost':
        return {}
      default:
        return {}
    }
  })()

  const iconSize = size === 'icon' || size === 'icon-sm' ? 16
    : size === 'xs' || size === 'sm' ? 13
    : 15

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={cn(buttonVariants({ variant, size }), className)}
      style={{ ...variantStyle, ...style }}
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
