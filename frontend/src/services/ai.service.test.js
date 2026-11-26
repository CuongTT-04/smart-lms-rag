import { expect, it, vi } from 'vitest'
import { apiRequest } from './api'
import { sendChat, sendChatFeedback, chatErrorMessage, advanceSummaryTask } from './ai.service'
vi.mock('./api', () => ({ apiRequest: vi.fn(async () => ({status:'ANSWERED'})) }))
it('uses the existing auth client with a bounded timeout specific to chat', async () => {
  const controller=new AbortController()
  await sendChat({question:'Q'}, {signal:controller.signal})
  expect(apiRequest).toHaveBeenCalledWith('/ai/chat/',expect.objectContaining({
    method:'POST',signal:controller.signal,timeoutMs:150000,body:JSON.stringify({question:'Q'})}))
})

it('explains output limits and busy generation separately from unavailable AI',()=>{
  expect(chatErrorMessage({data:{code:'OUTPUT_LIMIT_REACHED'}})).toContain('giới hạn')
  expect(chatErrorMessage({data:{code:'GENERATION_BUSY'}})).toContain('đang xử lý')
})

it('distinguishes AI quota, full queue and waiting timeout without showing provider details', () => {
  expect(chatErrorMessage({ status: 429, data: { code: 'AI_QUOTA_EXCEEDED', message: 'PRIVATE' } })).toContain('vẫn có thể đọc')
  expect(chatErrorMessage({ status: 429, data: { code: 'AI_QUEUE_FULL' } })).toContain('Hàng đợi')
  expect(chatErrorMessage({ status: 429, data: { code: 'AI_QUEUE_TIMEOUT' } })).toContain('chưa đến lượt')
})

it('explains verified validation failures without guessing details or displaying raw provider text',()=>{
  expect(chatErrorMessage({data:{code:'GENERATION_MISSING_CITATION',message:'PRIVATE provider text'}})).toContain('thiếu dẫn nguồn')
  expect(chatErrorMessage({data:{code:'GENERATION_INVALID_CITATION'}})).toContain('không có trong học liệu')
  expect(chatErrorMessage({data:{code:'GENERATION_INCOMPLETE_ANSWER'}})).toContain('đủ các bước')
  expect(chatErrorMessage({data:{code:'INVALID_GENERATION'}})).toContain('chưa cung cấp nguyên nhân chi tiết')
  expect(chatErrorMessage({data:{code:'UNKNOWN',message:'PRIVATE token'}})).not.toContain('PRIVATE')
})

it('persists or clears feedback through the authenticated API client', async () => {
  await sendChatFeedback('answer-id',null)
  expect(apiRequest).toHaveBeenLastCalledWith('/ai/chat/answer-id/feedback/',expect.objectContaining({method:'PATCH',body:'{"rating":null}'}))
})

it('distinguishes indexing and incomplete content from absent academic evidence', () => {
  expect(chatErrorMessage({ data: { code: 'RETRIEVAL_NOT_READY' } })).toContain('Chờ lập chỉ mục')
  expect(chatErrorMessage({ data: { code: 'GENERATION_INCOMPLETE_CONTENT' } })).toContain('câu dẫn')
})

it('preserves the long timeout for summary steps and explains transport failures', async () => {
  await advanceSummaryTask('summary-id')
  expect(apiRequest).toHaveBeenLastCalledWith('/ai/summaries/summary-id/', expect.objectContaining({ method: 'POST', timeoutMs: 150000 }))
  expect(chatErrorMessage({ status: 0 })).toContain('Mất kết nối')
  expect(chatErrorMessage({ status: 504 })).toContain('chưa phản hồi kịp')
  expect(chatErrorMessage({ status: 429 })).toContain('quá nhiều yêu cầu')
})

it('uses only known safe summary error codes, never raw provider messages', () => {
  expect(chatErrorMessage({ data: { code: 'SUMMARY_GENERATION_FAILED', remote_code: 'GENERATION_TIMEOUT' } })).toContain('quá lâu')
  expect(chatErrorMessage({ data: { code: 'SUMMARY_GENERATION_FAILED', remote_code: 'PRIVATE', message: 'PRIVATE' } })).not.toContain('PRIVATE')
  expect(chatErrorMessage({ status: 403, data: { code: 'AI_NOT_ALLOWED' } })).toContain('bài kiểm tra')
})
