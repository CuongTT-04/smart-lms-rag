import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearAccessToken, hasAccessToken, setAccessToken } from './api'
import { updateProfile, uploadAvatar } from './profile.service'

const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

describe('profile API transport', () => {
  beforeEach(() => { setAccessToken('profile-token'); vi.stubGlobal('fetch', vi.fn()) })
  afterEach(() => { clearAccessToken(); vi.unstubAllGlobals() })

  it('uploads multipart bytes with bearer auth and browser-generated content type', async () => {
    const user = { avatar_url: '/media/avatar.jpg' }
    fetch.mockResolvedValueOnce(json({ user }))
    const file = new File(['bytes'], 'avatar.jpg', { type: 'image/jpeg' })
    expect(await uploadAvatar(file)).toEqual(user)
    const [url, options] = fetch.mock.calls[0]
    expect(url).toBe('/api/users/me/avatar/')
    expect(options.method).toBe('POST')
    expect(options.body).toBeInstanceOf(FormData)
    expect(options.body.get('avatar')).toBe(file)
    expect(options.headers.Authorization).toBe('Bearer profile-token')
    expect(options.headers['Content-Type']).toBeUndefined()
  })

  it('clears the revoked access token after a successful password change', async () => {
    fetch.mockResolvedValueOnce(json({ user: {}, requires_login: true }))
    await updateProfile({ password: 'New-839!' })
    expect(hasAccessToken()).toBe(false)
    expect(fetch).toHaveBeenCalledWith('/api/users/me/', expect.objectContaining({ method: 'PATCH', body: JSON.stringify({ password: 'New-839!' }) }))
  })

  it('retains authentication after a validation failure or ordinary update', async () => {
    fetch.mockResolvedValueOnce(json({ phone: ['Invalid'] }, 400))
    await expect(updateProfile({ phone: 'bad' })).rejects.toMatchObject({ status: 400 })
    expect(hasAccessToken()).toBe(true)
    fetch.mockResolvedValueOnce(json({ user: {}, requires_login: false }))
    await updateProfile({ full_name: 'New name' })
    expect(hasAccessToken()).toBe(true)
  })
})
