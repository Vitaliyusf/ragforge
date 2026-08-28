/**
 * Render smoke tests for components extracted during the decomposition pass.
 *
 * These files carry no other coverage, and a missing import inside one of them
 * compiles cleanly but throws at render — exactly how AddMemoryForm shipped a
 * ReferenceError for MAX_CHARS. Mounting each component once catches that class
 * of mistake for the cost of a few lines.
 */
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import CategoryBadge from '@/features/memory/components/CategoryBadge'
import AddMemoryForm from '@/features/memory/components/AddMemoryForm'
import MemoryCard from '@/features/memory/components/MemoryCard'
import ServiceCard from '@/features/health/components/ServiceCard'
import CircuitBreakerPanel from '@/features/health/components/CircuitBreakerPanel'
import RateLimiterPanel from '@/features/health/components/RateLimiterPanel'
import MiniSparkline from '@/features/health/components/MiniSparkline'
import DocumentRow from '@/features/files/components/DocumentRow'

const noop = () => {}

const cases = [
  ['CategoryBadge', <CategoryBadge category="chat_insight" />],
  ['AddMemoryForm', <AddMemoryForm onAdd={noop} onCancel={noop} />],
  ['MemoryCard', <MemoryCard
    memory={{ memory_id: 'm1', content: 'hello', category: 'chat_insight', source: 'chat' }}
    isDeleting={false} onEdit={noop} onDelete={noop} />],
  ['ServiceCard', <ServiceCard name="gateway" info={{ status: 'healthy', latency_ms: 12 }} />],
  ['CircuitBreakerPanel', <CircuitBreakerPanel breakers={{ gateway: { state: 'closed', failure_count: 0 } }} />],
  ['CircuitBreakerPanel(empty)', <CircuitBreakerPanel breakers={{}} />],
  ['RateLimiterPanel', <RateLimiterPanel metrics={{ total_allowed: 10, total_rejected: 2, active_ip_buckets: 3 }} />],
  ['RateLimiterPanel(empty)', <RateLimiterPanel metrics={{}} />],
  ['MiniSparkline', <MiniSparkline data={[1, 2, 3, 4]} />],
  ['DocumentRow', <table><tbody><DocumentRow
    file={{ file_id: 'f1', filename: 'a.txt', size: 10, content_type: 'text/plain', status: 'complete' }}
    selected={false} isActive={false} isDeleting={false} requiresReview={false}
    onOpen={noop} onSelectChange={noop} onDelete={noop} onReview={noop} /></tbody></table>],
]

describe('Part 3 split components render', () => {
  for (const [name, element] of cases) {
    it(`${name} renders`, () => {
      expect(() => render(element)).not.toThrow()
    })
  }
})
