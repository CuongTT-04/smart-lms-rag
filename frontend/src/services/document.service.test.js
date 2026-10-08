import { beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('./api', () => ({ apiRequest: vi.fn() }))
import { apiRequest } from './api'
import { uploadDocument, retryDocument, listDocuments } from './document.service'

describe('document API integration', () => {
  beforeEach(() => vi.clearAllMocks())
  it('uses A API client with FormData and a stable idempotency key', async () => {
    const file=new File(['PDF'], 'lesson.pdf', { type:'application/pdf' })
    await uploadDocument('course', file, 'Lesson', 'stable-key')
    const [path, options]=apiRequest.mock.calls[0]
    expect(path).toBe('/courses/course/documents/')
    expect(options.body).toBeInstanceOf(FormData)
    expect(options.body.get('file')).toBe(file)
    expect(options.headers).toEqual({ 'Idempotency-Key':'stable-key' })
    expect(options.headers['Content-Type']).toBeUndefined()
  })
  it('retries a version using the same key supplied by the component', async () => {
    await retryDocument('doc', 'version', 'retry-key')
    expect(apiRequest).toHaveBeenCalledWith('/documents/doc/retry/', expect.objectContaining({
      body:JSON.stringify({ version_id:'version' }), headers: { 'Content-Type':'application/json', 'Idempotency-Key':'retry-key' },
    }))
  })
  it('paginates documents within the selected course', async () => {
    apiRequest.mockResolvedValueOnce({ results:[{ document_id:'doc' }], next:null })
    expect(await listDocuments('course')).toEqual([{ document_id:'doc' }])
  })
})
