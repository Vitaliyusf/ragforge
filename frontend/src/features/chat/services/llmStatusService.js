/** LLM runtime status API calls */
import { get } from '@/lib/http/client'

class LlmStatusService {
  /** Fetch whether the LLM backend (vLLM) has finished starting. */
  async getReadiness() {
    return await get('/v1/llm/ready')
  }
}

export default new LlmStatusService()
