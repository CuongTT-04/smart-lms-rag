import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { apiRequest, setAccessToken, clearAccessToken } from './api'
beforeEach(() => { vi.stubGlobal('fetch',vi.fn());setAccessToken('access') })
afterEach(() => { clearAccessToken();vi.unstubAllGlobals() })
it('rejects a shared refresh cookie that belongs to a different account', async () => {
  const jwt = (id) => `e30.${btoa(JSON.stringify({ user_id: id }))}.signature`
  setAccessToken(jwt('account-a'))
  fetch.mockResolvedValueOnce(new Response('{}', { status: 401 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ access: jwt('account-b') })))
  await expect(apiRequest('/notifications/')).rejects.toMatchObject({ status: 401 })
  expect(fetch).toHaveBeenCalledTimes(2)
})
it('does not overwrite a new login when an older refresh resolves late', async () => {
  let complete
  fetch.mockResolvedValueOnce(new Response('{}', { status: 401 }))
    .mockReturnValueOnce(new Promise((resolve) => { complete = resolve }))
  const pending = apiRequest('/notifications/')
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
  setAccessToken('new-login')
  complete(new Response(JSON.stringify({ access: 'old-refreshed' })))
  await expect(pending).rejects.toMatchObject({ status: 401 })
  fetch.mockResolvedValueOnce(new Response('{}'))
  await apiRequest('/users/me/')
  expect(fetch.mock.calls.at(-1)[1].headers.Authorization).toBe('Bearer new-login')
})
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
