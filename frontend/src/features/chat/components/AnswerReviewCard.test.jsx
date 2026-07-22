import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import AnswerReviewCard from './AnswerReviewCard'

describe('AnswerReviewCard', () => {
  it('renders verdict, scores, issues, and revision status', () => {
    render(
      <AnswerReviewCard
        review={{
          review_id: 'review-123',
          verdict: 'pass',
          groundedness_score: 0.92,
          completeness_score: 0.81,
          safety_score: 0.97,
          issues: ['Missing source on final claim'],
          revision_applied: true,
          model_name: 'eval-model',
          created_at: '2026-03-17T00:00:00Z',
        }}
      />
    )

    expect(screen.getByText(/Answer Review/i)).toBeInTheDocument()
    expect(screen.getByText(/pass/i)).toBeInTheDocument()
    expect(screen.getByText(/Revision applied/i)).toBeInTheDocument()
    expect(screen.getByText('92%')).toBeInTheDocument()
    expect(screen.getByText('81%')).toBeInTheDocument()
    expect(screen.getByText('97%')).toBeInTheDocument()
    expect(screen.getByText(/review-123/i)).toBeInTheDocument()
    expect(screen.getByText(/eval-model/i)).toBeInTheDocument()
    expect(screen.getByText(/Missing source on final claim/i)).toBeInTheDocument()
  })
})
