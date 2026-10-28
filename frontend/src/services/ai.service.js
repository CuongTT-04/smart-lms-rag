import { apiRequest } from './api'

export function listConversations(selector, { signal, cursor } = {}) {
  const query = new URLSearchParams(Object.entries(selector).filter(([, value]) => value != null))
  if (cursor) query.set('cursor', cursor)
  return apiRequest(`/ai/conversations/?${query}`, { signal })
}

export function createConversation(selector, { signal } = {}) {
  return apiRequest('/ai/conversations/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(selector), signal })
}

export function getConversation(id, { signal, before } = {}) {
  return apiRequest(`/ai/conversations/${encodeURIComponent(id)}/${before ? `?before=${encodeURIComponent(before)}` : ''}`, { signal })
}

export function sendChat(payload, { signal } = {}) {
  return apiRequest('/ai/chat/', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload), signal, timeoutMs: 150000 })
}

export function sendChatFeedback(answerId, rating, { signal } = {}) {
  return apiRequest(`/ai/chat/${encodeURIComponent(answerId)}/feedback/`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rating }), signal,
  })
}

export function chatErrorMessage(error) {
  const messages = {
    AI_NOT_ALLOWED: 'Không thể sử dụng AI trong khi làm bài kiểm tra.',
    SCOPE_CHANGED: 'Học liệu hoặc quyền truy cập đã thay đổi. Vui lòng tải lại.',
    GENERATION_UNAVAILABLE: 'ayo chưa sẵn sàng. Vui lòng thử lại sau.',
    RETRIEVAL_UNAVAILABLE: 'Chỉ mục học liệu chưa sẵn sàng. Vui lòng liên hệ giáo viên.',
    INVALID_GENERATION: 'Câu trả lời đã bị chặn ở bước kiểm tra phản hồi; dịch vụ AI chưa cung cấp nguyên nhân chi tiết. Hãy gửi lại hoặc chia nhỏ câu hỏi.',
    GENERATION_MISSING_CITATION: 'AI đã tạo câu trả lời nhưng thiếu dẫn nguồn từ học liệu nên chưa được hiển thị. Hãy gửi lại hoặc hỏi cụ thể hơn.',
    GENERATION_INVALID_CITATION: 'AI dẫn nguồn không có trong học liệu được cung cấp cho lượt hỏi này. Câu trả lời chưa được hiển thị để tránh dẫn nguồn sai. Hãy gửi lại câu hỏi.',
    GENERATION_INVALID_FORMAT: 'AI trả lời sai định dạng hoặc trộn câu trả lời với thông báo thiếu căn cứ. Câu trả lời chưa được hiển thị. Hãy gửi lại hoặc chia nhỏ câu hỏi.',
    GENERATION_EMPTY_RESPONSE: 'AI kết thúc xử lý nhưng không tạo được nội dung trả lời. Hãy gửi lại câu hỏi.',
    GENERATION_WRONG_LANGUAGE: 'AI trả lời lẫn ngôn ngữ ngoài yêu cầu nên câu trả lời chưa được hiển thị. Hãy yêu cầu trả lời bằng tiếng Việt và thử lại.',
    GENERATION_CHOICE_MISMATCH: 'Lựa chọn AI đưa ra không khớp với các phương án trong câu hỏi. Câu trả lời chưa được hiển thị. Hãy gửi lại câu hỏi kèm đầy đủ phương án.',
    OUTPUT_LIMIT_REACHED: 'Câu trả lời vượt giới hạn độ dài. Hãy thử câu hỏi cụ thể hơn.',
    INCOMPLETE_GENERATION: 'AI chưa hoàn tất câu trả lời. Vui lòng thử lại.',
    GENERATION_TIMEOUT: 'AI xử lý quá lâu. Vui lòng thử lại hoặc chia nhỏ câu hỏi.',
    GENERATION_BUSY: 'AI đang xử lý các yêu cầu khác. Vui lòng thử lại sau.',
    OUT_OF_MEMORY: 'Dịch vụ AI thiếu bộ nhớ xử lý. Vui lòng thử lại sau.',
    GENERATION_CONFIG_MISMATCH: 'Cấu hình trợ lý AI chưa đồng bộ với Kaggle. Vui lòng liên hệ người quản trị.',
    CONVERSATION_BUSY: 'Phiên chat đang xử lý một câu hỏi. Vui lòng đợi.',
    CHAT_SUPERSEDED: 'Lượt hỏi đã hết hiệu lực. Vui lòng tải lại phiên chat.',
    MESSAGE_CONFLICT: 'Lượt hỏi đã được sử dụng. Vui lòng gửi lại câu hỏi.',
  }
  if (error.status === 401) return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
  if (error.status === 404) return 'Học liệu không khả dụng hoặc bạn không có quyền truy cập.'
  return messages[error.data?.code] || 'Không thể gửi câu hỏi lúc này. Vui lòng thử lại.'
}
