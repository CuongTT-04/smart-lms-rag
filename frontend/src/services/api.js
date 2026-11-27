const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

let accessToken = null
let refreshPromise = null
let csrfPromise = null
let fallbackCsrfToken = null

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE'])

export function readCsrfToken() {
  if (typeof document !== 'undefined' && typeof document.cookie === 'string') {
    for (const part of document.cookie.split(';')) {
      const [rawName, ...rest] = part.trim().split('=')
      if (rawName === 'csrftoken') {
        const value = decodeURIComponent(rest.join('='))
        if (value) return value
      }
    }
  }
  return fallbackCsrfToken
}

export function clearCsrfFallback() {
  fallbackCsrfToken = null
}

function tokenSubject(token) {
  try {
    const payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(payload)).user_id
  } catch { return null }
}

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

async function fetchJson(path, { signal, headers, timeoutMs = 15000, ...options } = {}) {
  const timeout = AbortSignal.timeout(timeoutMs)
  const method = (options.method || 'GET').toUpperCase()
  const csrfToken = SAFE_METHODS.has(method) ? null : readCsrfToken()
  try {
    return await fetch(`${API_BASE}${path}`, {
      ...options,
      credentials: 'include',
      cache: 'no-store',
      signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
      headers: {
        Accept: 'application/json',
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {}),
        ...headers,
      },
    })
  } catch (error) {
    if (signal?.aborted) throw error
    throw new ApiError(0)
  }
}

export async function ensureCsrfCookie(signal) {
  if (!csrfPromise) {
    csrfPromise = fetchJson('/users/csrf/', { method: 'GET', signal })
      .then(async (response) => {
        const data = await response.json().catch(() => null)
        if (response.ok && typeof data?.csrfToken === 'string' && data.csrfToken) {
          fallbackCsrfToken = data.csrfToken
        }
      })
      .finally(() => { csrfPromise = null })
  }
  return csrfPromise
}

async function refreshAccessToken() {
  if (!refreshPromise) {
    const originalToken = accessToken
    const expectedSubject = tokenSubject(accessToken)
    const runRefresh = async (allowCsrfRetry) => {
      const response = await fetchJson('/users/token/refresh/', { method: 'POST' })
      const data = await response.json().catch(() => null)
      if (allowCsrfRetry && response.status === 403 && data?.code === 'CSRF_FAILED') {
        await ensureCsrfCookie()
        return runRefresh(false)
      }
      if (!response.ok || !data?.access) throw new ApiError(response.status, data)
      if (accessToken !== originalToken) throw new ApiError(401)
      if (expectedSubject && tokenSubject(data.access) !== expectedSubject) {
        clearAccessToken()
        window.dispatchEvent(new Event('ohayo:session-expired'))
        throw new ApiError(401, { detail: 'Tài khoản đăng nhập đã thay đổi ở cửa sổ khác. Vui lòng đăng nhập lại.' })
      }
      setAccessToken(data.access)
    }
    refreshPromise = runRefresh(true).finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

export async function apiRequest(path, options = {}) {
  const requestToken = accessToken
  const { responseType, skipCsrfRetry, ...fetchOptions } = options
  const method = (fetchOptions.method || 'GET').toUpperCase()
  const response = await fetchJson(path, fetchOptions)
  if (response.status === 401 && path !== '/users/login/' && path !== '/users/token/refresh/' && !options.skipRefresh) {
    try {
      await refreshAccessToken()
      return apiRequest(path, { ...options, skipRefresh: true })
    } catch (error) {
      if (accessToken === requestToken) clearAccessToken()
      throw error
    }
  }
  if (response.status === 204) return null
  if (response.ok && ['blob', 'image', 'video', 'submission', 'xlsx'].includes(responseType)) {
    const mime = (response.headers.get('Content-Type') || '').split(';')[0]
    const accepted = responseType === 'xlsx' ? ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'] : responseType === 'submission' ? ['application/pdf', 'image/png', 'image/jpeg'] : responseType === 'video' ? ['video/mp4', 'video/webm'] : responseType === 'image' ? ['image/png', 'image/jpeg', 'image/webp'] : ['application/pdf']
    if (!accepted.includes(mime)) throw new ApiError(502)
    return response.blob()
  }
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 403 && (data?.code === 'TEACHER_NOT_APPROVED' || data?.error?.code === 'TEACHER_NOT_APPROVED')) {
      window.dispatchEvent(new Event('ohayo:teaching-access-denied'))
    }
    if (!SAFE_METHODS.has(method) && !skipCsrfRetry && response.status === 403 && data?.code === 'CSRF_FAILED') {
      await ensureCsrfCookie(fetchOptions.signal)
      return apiRequest(path, { ...options, skipCsrfRetry: true })
    }
    throw new ApiError(response.status, data)
  }
  if (!data) throw new ApiError(502)
  return data
}
