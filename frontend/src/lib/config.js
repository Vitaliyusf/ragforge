/** Application configuration */
function parseBoolean(value, fallback = false) {
  if (value === undefined || value === null || value === '') {
    return fallback
  }
  return ['1', 'true', 'yes', 'on'].includes(String(value).toLowerCase())
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const RAG_WS_URL = process.env.NEXT_PUBLIC_RAG_WS_URL || 'http://localhost:8004'
const TRAINING_API_BASE_URL = process.env.NEXT_PUBLIC_TRAINING_API_BASE_URL || 'http://localhost:8009/v1/training'
const VLLM_BASE_URL = process.env.NEXT_PUBLIC_VLLM_BASE_URL || 'http://localhost:8008'

export const config = {
  apiBaseUrl: API_BASE_URL,
  ragWsUrl: RAG_WS_URL,
  trainingApiBaseUrl: TRAINING_API_BASE_URL,
  vllmBaseUrl: VLLM_BASE_URL,
  enableTrainingTab: parseBoolean(process.env.NEXT_PUBLIC_ENABLE_TRAINING_TAB, false),
  csrfCookieName: process.env.NEXT_PUBLIC_CSRF_COOKIE_NAME || 'ragapp_csrf',
}

export default config
