import { expect, it, vi } from 'vitest'
import { apiRequest } from './api'
import { sendChat, sendChatFeedback, chatErrorMessage } from './ai.service'
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

it('explains verified validation failures without guessing details or displaying raw provider text',()=>{
  expect(chatErrorMessage({data:{code:'GENERATION_MISSING_CITATION',message:'PRIVATE provider text'}})).toContain('thiếu dẫn nguồn')
  expect(chatErrorMessage({data:{code:'GENERATION_INVALID_CITATION'}})).toContain('không có trong học liệu')
  expect(chatErrorMessage({data:{code:'INVALID_GENERATION'}})).toContain('chưa cung cấp nguyên nhân chi tiết')
  expect(chatErrorMessage({data:{code:'UNKNOWN',message:'PRIVATE token'}})).not.toContain('PRIVATE')
})

it('persists or clears feedback through the authenticated API client', async () => {
  await sendChatFeedback('answer-id',null)
  expect(apiRequest).toHaveBeenLastCalledWith('/ai/chat/answer-id/feedback/',expect.objectContaining({method:'PATCH',body:'{"rating":null}'}))
})
