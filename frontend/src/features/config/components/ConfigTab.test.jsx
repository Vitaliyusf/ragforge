import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

const { getConfig } = vi.hoisted(() => ({ getConfig: vi.fn() }))

vi.mock('@/features/config', () => ({ configService: { getConfig } }))

import ConfigTab from './ConfigTab'

describe('ConfigTab', () => {
  it('shows deployment-owned effective config without mutation controls', async () => {
    getConfig.mockResolvedValue({
      configuration_policy: {
        owner: 'deployment',
        live_effective: [],
        restart_required: ['llm_implementation'],
      },
      llm_implementation: 'vllm',
      device: 'cuda',
      max_concurrent_requests: 4,
      ollama_url: 'http://ollama:11434',
      models: { summary: 'summary', metadata: 'metadata', rag_chat: 'chat', default: 'chat' },
      generation_params: {
        huggingface: { max_length: 512, temperature: 0.7, top_p: 0.9, do_sample: true },
        vllm: { max_tokens: 512, temperature: 0.7, top_p: 0.9, top_k: 50 },
      },
      vllm: { base_url: 'http://vllm:8000', max_model_len: 10240 },
      timeouts: { llm: 60, summary: 120, metadata: 60 },
    })

    render(<ConfigTab />)

    expect(await screen.findByRole('heading', { name: 'Effective configuration' })).toBeInTheDocument()
    expect(screen.getByText(/deployment-owned/i)).toBeInTheDocument()
    expect(screen.getByText(/recreate or restart the affected service/i)).toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(getConfig).toHaveBeenCalledTimes(1)
  })
})
