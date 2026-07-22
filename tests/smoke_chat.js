const { io } = require('socket.io-client')

const requestId = `smoke-${Date.now()}`
const socket = io(process.env.RAG_WS_URL || 'http://rag:8004', {
  transports: ['websocket'],
  timeout: 10_000,
})

let tokenCount = 0
let characterCount = 0

function finish(code, payload) {
  console.log(JSON.stringify(payload))
  socket.close()
  process.exit(code)
}

socket.on('connect', () => {
  socket.emit('question', {
    question: 'Explain retrieval augmented generation in one short sentence.',
    mode: 'regular',
    request_id: requestId,
    owner_id: 'smoke-user',
    owner_type: 'user',
  })
})

socket.on('token', (event) => {
  if (event.request_id !== requestId) return
  tokenCount += 1
  characterCount += String(event.data?.text_delta || event.data?.token || '').length
})

socket.on('done', (event) => {
  if (event.request_id !== requestId) return
  finish(0, {
    status: 'done',
    token_count: tokenCount,
    character_count: characterCount,
    data: event.data,
  })
})

socket.on('error', (event) => {
  if (!event.request_id || event.request_id === requestId) {
    finish(1, { status: 'error', event })
  }
})

socket.on('connect_error', (error) => {
  finish(1, { status: 'connect_error', message: error.message })
})

setTimeout(() => {
  finish(2, {
    status: 'timeout',
    token_count: tokenCount,
    character_count: characterCount,
  })
}, 240_000)
