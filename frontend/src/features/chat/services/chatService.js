/** Chat service for API calls */
import { get, post, del } from '@/lib/http/client'

class ChatService {
  /**
   * Send a chat message
   * @param {string} message - Message text
   * @param {boolean} useRag - Whether to use RAG
   * @param {string|null} model - Model to use
   * @param {string|null} chatId - Chat ID for conversation history context
   * @returns {Promise<Object>} Response data (includes response, sources, prompt_sent, history_sent)
   */
  async sendMessage(message, useRag = false, model = null, chatId = null) {
    const body = { message, use_rag: useRag, model }
    if (chatId) body.chat_id = chatId
    return await post('/v1/chat', body)
  }

  /**
   * Get available models
   * @returns {Promise<Object>} Models data
   */
  async getModels() {
    return await get('/v1/models')
  }

  /**
   * Get all chats
   * @returns {Promise<Object>} Chats data
   */
  async getChats() {
    return await get('/v1/chats')
  }

  /**
   * Create a new chat
   * @param {string} title - Chat title
   * @returns {Promise<Object>} Created chat data
   */
  async createChat(title = 'New Chat') {
    return await post(`/v1/chats?title=${encodeURIComponent(title)}`)
  }

  /**
   * Get messages for a chat
   * @param {string} chatId - Chat ID
   * @returns {Promise<Object>} Messages data
   */
  async getMessages(chatId) {
    return await get(`/v1/chats/${chatId}/messages`)
  }

  /**
   * Add a message to a chat
   * @param {string} chatId - Chat ID
   * @param {string} sender - Message sender
   * @param {string} message - Message text
   * @returns {Promise<Object>} Response data
   */
  async addMessage(chatId, sender, message) {
    return await post(`/v1/chats/${chatId}/messages`, {
      sender,
      message
    })
  }

  /**
   * Delete a chat
   * @param {string} chatId - Chat ID
   * @returns {Promise<Object>} Response data
   */
  async deleteChat(chatId) {
    return await del(`/v1/chats/${chatId}`)
  }

  /**
   * Process chat exit - generate headline and extract memory
   * @param {string} chatId - Chat ID
   * @returns {Promise<Object>} Response data
   */
  async processChatExit(chatId) {
    return await post(`/v1/chats/${chatId}/process-exit`)
  }

  /**
   * Update chat title
   * @param {string} chatId - Chat ID
   * @param {string} title - New title
   * @returns {Promise<Object>} Response data
   */
  async updateChatTitle(chatId, title) {
    return await post(`/v1/chats/${chatId}/title?title=${encodeURIComponent(title)}`)
  }
}

export default new ChatService()
