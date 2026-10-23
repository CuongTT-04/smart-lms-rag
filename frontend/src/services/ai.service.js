import { apiRequest } from './api'

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
    GENERATION_UNAVAILABLE: 'Trợ lý AI chưa sẵn sàng. Vui lòng thử lại sau.',
    RETRIEVAL_UNAVAILABLE: 'Chỉ mục học liệu chưa sẵn sàng. Vui lòng liên hệ giáo viên.',
    INVALID_GENERATION: 'Phản hồi AI chưa hợp lệ. Vui lòng thử lại.',
    OUTPUT_LIMIT_REACHED: 'Câu trả lời vượt giới hạn độ dài. Hãy thử câu hỏi cụ thể hơn.',
    INCOMPLETE_GENERATION: 'AI chưa hoàn tất câu trả lời. Vui lòng thử lại.',
    GENERATION_TIMEOUT: 'AI xử lý quá lâu. Vui lòng thử lại hoặc chia nhỏ câu hỏi.',
    GENERATION_BUSY: 'AI đang xử lý các yêu cầu khác. Vui lòng thử lại sau.',
    OUT_OF_MEMORY: 'Dịch vụ AI thiếu bộ nhớ xử lý. Vui lòng thử lại sau.',
    GENERATION_CONFIG_MISMATCH: 'Cấu hình trợ lý AI chưa đồng bộ với Kaggle. Vui lòng liên hệ người quản trị.',
  }
  if (error.status === 401) return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
  if (error.status === 404) return 'Học liệu không khả dụng hoặc bạn không có quyền truy cập.'
  return messages[error.data?.code] || 'Không thể gửi câu hỏi lúc này. Vui lòng thử lại.'
}
