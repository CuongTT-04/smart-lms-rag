import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiRequest, clearAccessToken, hasAccessToken, setAccessToken } from './api'
import { login, logout, currentUser, authErrorMessage, registerAccount, requestPasswordReset, confirmPasswordReset, accountFieldErrors } from './auth.service'

const user = { username: 'student', full_name: 'Học viên OHAYO', role: 'STUDENT', status: 'ACTIVE' }
const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

describe('JWT authentication', () => {
  beforeEach(() => { clearAccessToken(); vi.stubGlobal('fetch', vi.fn()) })
  afterEach(() => vi.unstubAllGlobals())

  it('logs in without CSRF, keeps access only in memory, and preserves password spaces', async () => {
    fetch.mockResolvedValueOnce(json({ user, access: 'access-token' }))
    expect(await login(' student ', ' secret ')).toEqual(user)
    expect(fetch).toHaveBeenCalledWith('/api/users/login/', expect.objectContaining({
      method: 'POST', credentials: 'include',
      headers: expect.not.objectContaining({ 'X-CSRFToken': expect.anything() }),
      body: JSON.stringify({ username: 'student', password: ' secret ' }),
    }))
    fetch.mockResolvedValueOnce(json({ user }))
    await currentUser()
    expect(fetch).toHaveBeenLastCalledWith('/api/users/me/', expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer access-token' }),
    }))
  })

  it('refreshes an expired access token once and retries the original request', async () => {
    setAccessToken('expired-access')
    fetch
      .mockResolvedValueOnce(json({ detail: 'expired' }, 401))
      .mockResolvedValueOnce(json({ access: 'fresh-access' }))
      .mockResolvedValueOnce(json({ user }))
    expect(await currentUser()).toEqual(user)
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/users/token/refresh/', expect.objectContaining({ method: 'POST', credentials: 'include' }))
    expect(fetch).toHaveBeenNthCalledWith(3, '/api/users/me/', expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer fresh-access' }) }))
  })

  it('restores an existing browser session without calling the protected profile endpoint first', async () => {
    fetch.mockResolvedValueOnce(json({ authenticated: true, user, access: 'restored-access' }))
    expect(await currentUser()).toEqual(user)
    expect(fetch).toHaveBeenCalledWith('/api/users/session/', expect.objectContaining({ credentials: 'include' }))

    fetch.mockResolvedValueOnce(json({ user }))
    expect(await currentUser()).toEqual(user)
    expect(fetch).toHaveBeenLastCalledWith('/api/users/me/', expect.objectContaining({
      headers: expect.objectContaining({ Authorization: 'Bearer restored-access' }),
    }))
  })

  it('logs out with bearer auth and accepts empty 204', async () => {
    fetch.mockResolvedValueOnce(json({ user, access: 'access-token' }))
    await login('student', 'secret')
    fetch.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await expect(logout()).resolves.toBeUndefined()
    expect(fetch).toHaveBeenLastCalledWith('/api/users/logout/', expect.objectContaining({
      method: 'POST', headers: expect.objectContaining({ Authorization: 'Bearer access-token' }),
    }))
  })

  it.each([400, 403, 429])('preserves HTTP %s and provides a Vietnamese error', async (status) => {
    fetch.mockResolvedValueOnce(json({ detail: 'server error' }, status))
    const error = await apiRequest('/users/me/').catch((failure) => failure)
    expect(error.status).toBe(status)
    expect(authErrorMessage(error)).not.toContain('server error')
    expect(authErrorMessage(error)).toMatch(/Vui lòng|Tên đăng nhập|quyền/)
  })

  it('treats an anonymous browser session as a normal signed-out state', async () => {
    fetch.mockResolvedValueOnce(json({ authenticated: false }))
    await expect(currentUser()).resolves.toBeNull()
    expect(fetch).toHaveBeenCalledWith('/api/users/session/', expect.objectContaining({ credentials: 'include' }))
  })

  it('handles HTML upstream errors and cancellation', async () => {
    fetch.mockResolvedValueOnce(new Response('<html>Bad gateway</html>', { status: 502 }))
    await expect(currentUser()).rejects.toMatchObject({ status: 502 })
    const controller = new AbortController()
    controller.abort()
    fetch.mockRejectedValueOnce(new DOMException('Aborted', 'AbortError'))
    await expect(currentUser(controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
  })

  it('registers with the chosen role and does not establish a login session', async () => {
    fetch.mockResolvedValueOnce(json({ user: { ...user, role: 'TEACHER' } }, 201))
    const payload = { username: ' teacher ', email: ' teacher@example.com ', full_name: ' Giáo viên ', role: 'TEACHER', password: ' secret ', password_confirm: ' secret ' }
    expect((await registerAccount(payload)).role).toBe('TEACHER')
    expect(fetch).toHaveBeenCalledWith('/api/users/register/', expect.objectContaining({
      method: 'POST', body: JSON.stringify({ ...payload, username: 'teacher', email: 'teacher@example.com', full_name: 'Giáo viên' }),
    }))
    expect(hasAccessToken()).toBe(false)
  })

  it('requests reset through the public email endpoint', async () => {
    fetch.mockResolvedValueOnce(json({ detail: 'generic' }))
    await requestPasswordReset(' student@example.com ')
    expect(fetch).toHaveBeenCalledWith('/api/users/password-reset/', expect.objectContaining({ method: 'POST', body: JSON.stringify({ email: 'student@example.com' }) }))
  })

  it('clears access only after successful reset and preserves password spaces', async () => {
    setAccessToken('old-access')
    fetch.mockResolvedValueOnce(json({ token: ['expired'] }, 400))
    const payload = { uid: 'uid', token: 'token', password: ' new secret ', password_confirm: ' new secret ' }
    await expect(confirmPasswordReset(payload)).rejects.toMatchObject({ status: 400 })
    expect(hasAccessToken()).toBe(true)
    fetch.mockResolvedValueOnce(json({ detail: 'success' }))
    await confirmPasswordReset(payload)
    expect(fetch).toHaveBeenLastCalledWith('/api/users/password-reset/confirm/', expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }))
    expect(hasAccessToken()).toBe(false)
  })

  it('maps known field errors without echoing arbitrary backend text or secrets', () => {
    const errors = accountFieldErrors({ status: 400, data: { token: ['secret-token'], password: ['raw-server-message'], unknown: ['secret'] } })
    expect(Object.keys(errors)).toEqual(['token', 'password'])
    expect(JSON.stringify(errors)).not.toMatch(/secret|raw-server/)
  })
})
