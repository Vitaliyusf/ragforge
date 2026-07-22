import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Merge Tailwind classes safely, resolving conflicts intelligently. */
export function cn(...inputs) {
  return twMerge(clsx(inputs))
}
