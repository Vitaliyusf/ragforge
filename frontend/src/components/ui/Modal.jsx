'use client'

import { useEffect, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { AnimatePresence, motion } from 'framer-motion'
import { X, AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'

const MODAL_Z = 2147483647

function getSizeClass(size, variant) {
  if (variant === 'drawer') {
    if (size === 'lg') return 'max-w-2xl'
    if (size === 'xl') return 'max-w-3xl'
    return 'max-w-xl'
  }
  if (size === 'sm')  return 'max-w-sm'
  if (size === 'lg')  return 'max-w-2xl'
  if (size === 'xl')  return 'max-w-4xl'
  return 'max-w-lg'
}

export default function Modal({
  open,
  onOpenChange,
  title,
  children,
  showClose = true,
  size = 'default',
  variant = 'modal',
}) {
  const [container, setContainer] = useState(null)
  useEffect(() => {
    setContainer(typeof document !== 'undefined' ? document.body : null)
  }, [])

  const sizeClass = getSizeClass(size, variant)

  const sharedContentStyle = {
    background: 'var(--surface-elevated)',
    border:     '1px solid var(--border)',
    boxShadow:  'var(--shadow-xl)',
  }

  const CloseButton = () => (
    <Dialog.Close asChild>
      <button
        className={cn(
          'rounded-lg p-2 transition-colors outline-none',
          'focus-visible:ring-2 focus-visible:ring-[var(--ring)]'
        )}
        style={{ color: 'var(--fg-soft)' }}
        onMouseEnter={e => { e.currentTarget.style.background = 'var(--surface-hover)'; e.currentTarget.style.color = 'var(--fg)' }}
        onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--fg-soft)' }}
        aria-label="Close"
      >
        <X size={18} />
      </button>
    </Dialog.Close>
  )

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal container={container ?? undefined}>
        <AnimatePresence>
          {open ? (
            <>
              <Dialog.Overlay asChild>
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.15 }}
                  className="fixed inset-0 backdrop-blur-sm"
                  style={{ background: 'rgba(0,0,0,0.6)', zIndex: MODAL_Z }}
                />
              </Dialog.Overlay>

              <Dialog.Content asChild>
                {variant === 'drawer' ? (
                  <motion.div
                    initial={{ opacity: 0, x: 48 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: 48 }}
                    transition={{ type: 'spring', damping: 28, stiffness: 320 }}
                    className="fixed inset-y-0 right-0 flex w-full justify-end p-3"
                    style={{ zIndex: MODAL_Z + 1 }}
                  >
                    <div
                      className={cn('flex h-full w-full flex-col overflow-hidden rounded-2xl', sizeClass)}
                      style={sharedContentStyle}
                    >
                      <div
                        className="flex items-center justify-between px-5 py-4 border-b"
                        style={{ borderColor: 'var(--border)' }}
                      >
                        <Dialog.Title className="text-sm font-semibold" style={{ color: 'var(--fg)' }}>
                          {title}
                        </Dialog.Title>
                        {showClose && <CloseButton />}
                      </div>
                      <div className="flex-1 overflow-y-auto p-5">{children}</div>
                    </div>
                  </motion.div>
                ) : (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="fixed inset-0 flex items-center justify-center overflow-auto p-4"
                    style={{ zIndex: MODAL_Z + 1 }}
                  >
                    <motion.div
                      initial={{ opacity: 0, scale: 0.96, y: 8 }}
                      animate={{ opacity: 1, scale: 1,    y: 0 }}
                      exit={{ opacity: 0, scale: 0.96,    y: 8 }}
                      transition={{ type: 'spring', damping: 28, stiffness: 360 }}
                      className={cn('my-auto max-h-[90vh] w-full overflow-y-auto rounded-2xl', sizeClass)}
                      style={sharedContentStyle}
                    >
                      <div className="p-5">
                        <div className="mb-4 flex items-center justify-between gap-3">
                          <Dialog.Title className="text-sm font-semibold" style={{ color: 'var(--fg)' }}>
                            {title}
                          </Dialog.Title>
                          {showClose && <CloseButton />}
                        </div>
                        {children}
                      </div>
                    </motion.div>
                  </motion.div>
                )}
              </Dialog.Content>
            </>
          ) : null}
        </AnimatePresence>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

export function ConfirmModal({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = 'Confirm',
  cancelLabel  = 'Cancel',
  onConfirm,
  variant = 'primary',
  loading = false,
}) {
  const handleConfirm = async () => {
    await onConfirm?.()
    onOpenChange(false)
  }

  return (
    <Modal open={open} onOpenChange={onOpenChange} title={title} showClose={!loading} size="sm">
      <div className="space-y-5">
        {description && (
          <div className="flex gap-3">
            {variant === 'danger' && (
              <AlertTriangle size={18} className="shrink-0 mt-0.5" style={{ color: 'var(--warning)' }} />
            )}
            <p className="text-sm leading-relaxed" style={{ color: 'var(--fg-muted)' }}>
              {description}
            </p>
          </div>
        )}
        <div className="flex justify-end gap-2">
          <Dialog.Close asChild>
            <button
              disabled={loading}
              className="px-4 py-2 rounded-lg text-sm font-medium transition-colors outline-none"
              style={{ background: 'var(--surface-hover)', color: 'var(--fg-muted)' }}
              onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-active)'}
              onMouseLeave={e => e.currentTarget.style.background = 'var(--surface-hover)'}
            >
              {cancelLabel}
            </button>
          </Dialog.Close>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="px-4 py-2 rounded-lg text-sm font-medium text-white transition-all outline-none disabled:opacity-60"
            style={{
              background: variant === 'danger' ? 'var(--danger)' : 'var(--gradient-primary)',
            }}
            onMouseEnter={e => e.currentTarget.style.filter = 'brightness(1.1)'}
            onMouseLeave={e => e.currentTarget.style.filter = ''}
          >
            {loading ? 'Loading…' : confirmLabel}
          </button>
        </div>
      </div>
    </Modal>
  )
}
