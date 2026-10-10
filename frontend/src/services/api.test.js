import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { apiRequest, setAccessToken, clearAccessToken } from './api'
beforeEach(() => { vi.stubGlobal('fetch',vi.fn());setAccessToken('access') })
afterEach(() => { clearAccessToken();vi.unstubAllGlobals() })
it('returns a PDF blob through the existing bearer client', async () => {
  fetch.mockResolvedValue(new Response('%PDF-fixture',{headers:{'Content-Type':'application/pdf'}}))
  const blob=await apiRequest('/documents/doc/view/',{responseType:'blob'})
  expect(blob).toBeInstanceOf(Blob)
  expect(fetch).toHaveBeenCalledWith('/api/documents/doc/view/',expect.objectContaining({headers:expect.objectContaining({Authorization:'Bearer access'})}))
})
it('retains structured errors for denied binary requests', async () => {
  fetch.mockResolvedValue(new Response(JSON.stringify({error:{code:'DOWNLOAD_DISABLED'}}),{status:403}))
  await expect(apiRequest('/documents/doc/download/',{responseType:'blob'})).rejects.toMatchObject({status:403,data:{error:{code:'DOWNLOAD_DISABLED'}}})
})
it('refreshes JWT before retrying a binary request', async () => {
  fetch.mockResolvedValueOnce(new Response('{}',{status:401}))
    .mockResolvedValueOnce(new Response(JSON.stringify({access:'new-access'})))
    .mockResolvedValueOnce(new Response('%PDF-fixture',{headers:{'Content-Type':'application/pdf'}}))
  expect(await apiRequest('/documents/doc/view/',{responseType:'blob'})).toBeInstanceOf(Blob)
  expect(fetch.mock.calls[2][1].headers.Authorization).toBe('Bearer new-access')
})

it('returns authenticated announcement images and rejects non-image responses', async () => {
  fetch.mockResolvedValueOnce(new Response('png', { headers: { 'Content-Type': 'image/png' } }))
  expect(await apiRequest('/courses/c/classrooms/r/announcements/a/image/', { responseType: 'image' })).toBeInstanceOf(Blob)
  fetch.mockResolvedValueOnce(new Response('<svg/>', { headers: { 'Content-Type': 'image/svg+xml' } }))
  await expect(apiRequest('/courses/c/classrooms/r/announcements/a/image/', { responseType: 'image' })).rejects.toMatchObject({ status: 502 })
})
