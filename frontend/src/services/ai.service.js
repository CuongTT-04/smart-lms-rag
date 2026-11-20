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

export function getSummaryTask(id, { signal } = {}) {
  return apiRequest(`/ai/summaries/${encodeURIComponent(id)}/`, { signal })
}

export function advanceSummaryTask(id, { signal } = {}) {
  return apiRequest(`/ai/summaries/${encodeURIComponent(id)}/`, { method: 'POST', signal, timeoutMs: 150000 })
}

export function chatErrorMessage(error) {
  const messages = {
    AI_NOT_ALLOWED: 'Không thể sử dụng AI trong khi làm bài kiểm tra.',
    SCOPE_CHANGED: 'Học liệu hoặc quyền truy cập đã thay đổi. Vui lòng tải lại.',
    GENERATION_UNAVAILABLE: 'ayo chưa sẵn sàng. Vui lòng thử lại sau.',
    RETRIEVAL_UNAVAILABLE: 'Chỉ mục học liệu chưa sẵn sàng. Vui lòng liên hệ giáo viên.',
    RETRIEVAL_NOT_READY: 'Học liệu đã chọn chưa sẵn sàng cho AI. Chờ lập chỉ mục hoàn tất rồi thử lại.',
    SUMMARY_SCOPE_INVALID: 'Chọn đúng một học liệu và phạm vi tối đa 20 trang PDF hợp lệ.',
    SUMMARY_SOURCE_INCOMPLETE: 'Chưa đọc đủ văn bản của các trang đã chọn. Hãy chọn phạm vi khác hoặc kiểm tra lập chỉ mục PDF.',
    SUMMARY_GENERATION_FAILED: 'Chưa tạo được bản tóm tắt hoàn chỉnh. Vui lòng thử lại hoặc chọn ít trang hơn.',
    SUMMARY_EXPIRED: 'Tiến trình tóm tắt đã hết thời gian. Vui lòng tạo lại.',
    INVALID_GENERATION: 'Câu trả lời đã bị chặn ở bước kiểm tra phản hồi; dịch vụ AI chưa cung cấp nguyên nhân chi tiết. Hãy gửi lại hoặc chia nhỏ câu hỏi.',
    GENERATION_MISSING_CITATION: 'AI đã tạo câu trả lời nhưng thiếu dẫn nguồn từ học liệu nên chưa được hiển thị. Hãy gửi lại hoặc hỏi cụ thể hơn.',
    GENERATION_INVALID_CITATION: 'AI dẫn nguồn không có trong học liệu được cung cấp cho lượt hỏi này. Câu trả lời chưa được hiển thị để tránh dẫn nguồn sai. Hãy gửi lại câu hỏi.',
    GENERATION_INVALID_FORMAT: 'AI trả lời sai định dạng hoặc trộn câu trả lời với thông báo thiếu căn cứ. Câu trả lời chưa được hiển thị. Hãy gửi lại hoặc chia nhỏ câu hỏi.',
    GENERATION_INCOMPLETE_ANSWER: 'AI chưa trình bày đủ các bước trong học liệu. Hãy hỏi từng phần của quy trình.',
    GENERATION_INCOMPLETE_CONTENT: 'AI chưa trả lời đủ nội dung hoặc mới đưa câu dẫn/câu dở dang. Hãy thử lại hoặc hỏi cụ thể từng ý trong học liệu.',
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
  if (error.data?.code === 'SUMMARY_GENERATION_FAILED' &&
      ['GENERATION_TIMEOUT', 'OUTPUT_LIMIT_REACHED', 'INCOMPLETE_GENERATION', 'OUT_OF_MEMORY', 'GENERATION_UNAVAILABLE'].includes(error.data.remote_code)) {
    return messages[error.data.remote_code]
  }
  if (error.status === 0) return 'Mất kết nối tới máy chủ. Vui lòng kiểm tra kết nối rồi thử lại.'
  if ([502, 504].includes(error.status)) return 'Máy chủ chưa phản hồi kịp. Vui lòng thử lại sau.'
  if (error.status === 429) return 'Có quá nhiều yêu cầu. Vui lòng đợi rồi thử lại.'
  return messages[error.data?.code] || 'Không thể gửi câu hỏi lúc này. Vui lòng thử lại.'
}
