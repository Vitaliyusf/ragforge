/**
 * Scaling maths for the time series chart.
 *
 * A zero-range series divided by its range yields NaN coordinates, which
 * produce an SVG that renders nothing and reports no error — so the guard
 * against it is worth a test of its own.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import TimeSeries from './TimeSeries'

describe('TimeSeries', () => {
  it('keeps NaN out of the path when every value is identical', () => {
    const { container } = render(
      <TimeSeries
        label="Flat series"
        series={[{ name: 'flat', points: [[1, 5], [2, 5], [3, 5]] }]}
      />
    )

    const paths = container.querySelectorAll('path')
    expect(paths.length).toBeGreaterThan(0)
    for (const path of paths) {
      expect(path.getAttribute('d')).not.toMatch(/NaN/)
    }
  })

  it('keeps NaN out of the axis labels when every value is identical', () => {
    const { container } = render(
      <TimeSeries series={[{ name: 'flat', points: [[1, 5], [2, 5]] }]} />
    )
    expect(container.textContent).not.toMatch(/NaN/)
  })

  it('keeps NaN out of the path when every timestamp is identical', () => {
    const { container } = render(
      <TimeSeries series={[{ name: 'same instant', points: [[7, 1], [7, 4]] }]} />
    )
    for (const path of container.querySelectorAll('path')) {
      expect(path.getAttribute('d')).not.toMatch(/NaN/)
    }
  })

  it('renders nothing for a single point rather than throwing', () => {
    let container
    expect(() => {
      ;({ container } = render(<TimeSeries series={[{ name: 'one', points: [[1, 5]] }]} />))
    }).not.toThrow()
    expect(container.querySelector('svg')).toBeNull()
  })

  it('renders nothing for an empty series list', () => {
    const { container } = render(<TimeSeries series={[]} />)
    expect(container.querySelector('svg')).toBeNull()
  })

  it('exposes an accessible name summarising the chart', () => {
    render(
      <TimeSeries
        label="Turn latency"
        series={[{ name: 'p95', points: [[1, 2], [2, 3]] }]}
      />
    )
    expect(screen.getByRole('img', { name: /Turn latency.*p95/i })).toBeInTheDocument()
  })

  it('shows a legend only when more than one series is present', () => {
    const one = render(<TimeSeries series={[{ name: 'solo', points: [[1, 1], [2, 2]] }]} />)
    expect(one.queryByText('solo')).toBeNull()
    one.unmount()

    render(
      <TimeSeries
        series={[
          { name: 'first', points: [[1, 1], [2, 2]] },
          { name: 'second', points: [[1, 3], [2, 4]] },
        ]}
      />
    )
    expect(screen.getByText('first')).toBeInTheDocument()
    expect(screen.getByText('second')).toBeInTheDocument()
  })
})
