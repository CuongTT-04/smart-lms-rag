import { afterEach, expect, it, vi } from 'vitest'
import { listInstitutions } from './institution.service'
import { clearAccessToken } from './api'

afterEach(() => { clearAccessToken(); vi.unstubAllGlobals() })
it('encodes lookup query, limits results and forwards cancellation', async () => {
  const controller = new AbortController()
  const response = { results: [], has_more: false, next_offset: null }
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(response))))
  expect(await listInstitutions('Bách khoa & HUST', controller.signal)).toEqual(response)
  expect(fetch.mock.calls[0][0]).toBe('/api/users/institutions/?q=B%C3%A1ch+khoa+%26+HUST&limit=20')
  expect(fetch.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal)
})
