'use client'

import Modal from '@/components/ui/Modal'

function SummaryModal({ open, onClose, file, summary }) {
  const text =
    typeof summary === 'string'
      ? summary
      : summary?.summary
        || summary?.text
        || summary?.content
        || (summary ? JSON.stringify(summary, null, 2) : '')

  return (
    <Modal
      open={open}
      onOpenChange={(next) => { if (!next) onClose() }}
      title="Summary"
      size="lg"
    >
      {file?.filename ? (
        <p className="-mt-2 mb-3 truncate text-[13px] text-text-secondary">{file.filename}</p>
      ) : null}
      <div className="max-h-[60vh] overflow-y-auto scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent">
        <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-text-secondary">
          {text || 'No summary available for this file.'}
        </p>
      </div>
    </Modal>
  )
}

export default SummaryModal
