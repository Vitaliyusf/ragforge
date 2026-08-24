'use client'

import { useState } from 'react'
import { GitBranch, MessageSquareWarning, ThumbsDown, ThumbsUp } from 'lucide-react'
import Button from '@/components/ui/Button'

function statusText(state, defaultLabel) {
  if (!state || state.status === 'idle') return defaultLabel
  if (state.status === 'sending') return 'Sending...'
  if (state.status === 'sent') return 'Sent'
  return state.error || 'Failed'
}

export default function FeedbackControls({
  turnId,
  feedback,
  onAnswerFeedback,
  onFlowFeedback,
}) {
  const [comment, setComment] = useState('')

  return (
    <div className="mt-2 w-full rounded-2xl border border-border bg-bg-tertiary/60 p-3">
      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <div className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-text-muted">
            <ThumbsUp size={12} />
            Answer Feedback
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onAnswerFeedback(turnId, { label: 'helpful', rating: 'positive', comment })}
              disabled={feedback?.answer?.status === 'sending'}
              leftIcon={<ThumbsUp size={14} />}
            >
              Helpful
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onAnswerFeedback(turnId, { label: 'not_helpful', rating: 'negative', comment })}
              disabled={feedback?.answer?.status === 'sending'}
              leftIcon={<ThumbsDown size={14} />}
            >
              Needs work
            </Button>
          </div>
          <div className="mt-2 text-xs text-text-muted">
            {statusText(feedback?.answer, 'Send answer feedback')}
          </div>
        </div>

        <div>
          <div className="mb-2 flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wide text-text-muted">
            <GitBranch size={12} />
            Flow Feedback
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onFlowFeedback(turnId, { category: 'flow_clear', label: 'clear', comment })}
              disabled={feedback?.flow?.status === 'sending'}
              leftIcon={<GitBranch size={14} />}
            >
              Clear flow
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onFlowFeedback(turnId, { category: 'flow_confusing', label: 'confusing', comment })}
              disabled={feedback?.flow?.status === 'sending'}
              leftIcon={<MessageSquareWarning size={14} />}
            >
              Confusing flow
            </Button>
          </div>
          <div className="mt-2 text-xs text-text-muted">
            {statusText(feedback?.flow, 'Send flow feedback')}
          </div>
        </div>
      </div>

      <label className="mt-3 block">
        <span className="mb-1 block text-xs font-medium text-text-muted">Optional note</span>
        <textarea
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          placeholder="Add a short note for this answer or flow..."
          className="h-20 w-full resize-none rounded-xl border border-border bg-bg-elevated px-3 py-2 text-[15px] text-text-primary outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20"
        />
      </label>
    </div>
  )
}

