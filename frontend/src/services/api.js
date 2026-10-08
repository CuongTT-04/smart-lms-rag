const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

let accessToken = null
let refreshPromise = null

export class ApiError extends Error {
  constructor(status, data = null) {
    super(`API request failed (${status})`)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

export function setAccessToken(token) {
  accessToken = token || null
}

export function clearAccessToken() {
  accessToken = null
}

export function hasAccessToken() {
  return Boolean(accessToken)
}

async function fetchJson(path, { signal, headers, ...options } = {}) {
  const timeout = AbortSignal.timeout(15000)
  try {
    return await fetch(`${API_BASE}${path}`, {
      ...options,
      credentials: 'include',
      cache: 'no-store',
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      headers: { Accept: 'application/json', ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}), ...headers },
    })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError(0)
  }
}

async function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = fetchJson('/users/token/refresh/', { method: 'POST' })
      .then(async (response) => {
        const data = await response.json().catch(() => null)
        if (!response.ok || !data?.access) throw new ApiError(response.status, data)
        setAccessToken(data.access)
      })
      .finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

export async function apiRequest(path, options = {}) {
  const response = await fetchJson(path, options)
  if (response.status === 401 && path !== '/users/login/' && path !== '/users/token/refresh/' && !options.skipRefresh) {
    try {
      await refreshAccessToken()
      return apiRequest(path, { ...options, skipRefresh: true })
    } catch (error) {
      clearAccessToken()
      throw error
    }
  }
  if (response.status === 204) return null
  const data = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, data)
  if (!data) throw new ApiError(502)
  return data
}
