import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { apiRequest, clearAccessToken, clearCsrfFallback, hasAccessToken, setAccessToken } from './api'
beforeEach(() => { vi.stubGlobal('fetch', vi.fn()); setAccessToken('access'); clearCsrfFallback(); document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/' })
afterEach(() => { clearAccessToken(); clearCsrfFallback(); document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'; vi.unstubAllGlobals() })
it.each([{ code: 'TEACHER_NOT_APPROVED' }, { error: { code: 'TEACHER_NOT_APPROVED' } }])('signals teaching denial without logging out or retrying the write', async data => {
  const listener = vi.fn()
  window.addEventListener('ohayo:teaching-access-denied', listener)
  try {
    fetch.mockResolvedValueOnce(new Response(JSON.stringify(data), { status: 403 }))
    await expect(apiRequest('/courses/', { method: 'POST' })).rejects.toMatchObject({ status: 403 })
    expect(listener).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(hasAccessToken()).toBe(true)
  } finally { window.removeEventListener('ohayo:teaching-access-denied', listener) }
})
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

it('sends current csrftoken cookie on unsafe requests and auto-refresh, and recovers on CSRF_FAILED', async () => {
  document.cookie = 'csrftoken=token-v1; path=/'
  fetch.mockResolvedValueOnce(new Response('{}', { status: 401 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ access: 'refreshed-access' })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true })))
  await apiRequest('/users/me/', { method: 'PATCH', body: '{}' })
  expect(fetch.mock.calls[0][1].headers['X-CSRFToken']).toBe('token-v1')
  expect(fetch.mock.calls[1][0]).toBe('/api/users/token/refresh/')
  expect(fetch.mock.calls[1][1].headers['X-CSRFToken']).toBe('token-v1')

  // Rotated cookie is read dynamically on the next POST.
  document.cookie = 'csrftoken=token-v2; path=/'
  fetch.mockResolvedValueOnce(new Response(null, { status: 204 }))
  await apiRequest('/users/logout/', { method: 'POST' })
  expect(fetch.mock.calls[3][1].headers['X-CSRFToken']).toBe('token-v2')

  // Missing cookie + 403 CSRF_FAILED fetches /users/csrf/ once and retries.
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/'
  fetch.mockResolvedValueOnce(new Response(JSON.stringify({ code: 'CSRF_FAILED' }), { status: 403 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ csrfToken: 'bootstrapped-token' }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ user: { id: '1' }, access: 'a' }), { status: 200 }))
  await apiRequest('/users/login/', { method: 'POST', body: '{}' })
  expect(fetch.mock.calls[5][0]).toBe('/api/users/csrf/')
  expect(fetch.mock.calls[6][1].headers['X-CSRFToken']).toBe('bootstrapped-token')
})
