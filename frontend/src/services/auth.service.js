import { apiRequest, clearAccessToken, hasAccessToken, setAccessToken } from './api'
import { PASSWORD_REQUIREMENTS } from '../utils/password'

export async function login(username, password) {
  const { user, access } = await apiRequest('/users/login/', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: username.trim(), password }),
  })
  setAccessToken(access)
  return user
}

export async function currentUser(signal) {
  if (!hasAccessToken()) {
    const session = await apiRequest('/users/session/', { signal, skipRefresh: true })
    if (!session.authenticated) return null
    setAccessToken(session.access)
    return session.user
  }
  const { user } = await apiRequest('/users/me/', { signal })
  return user
}

export async function logout() {
  try { await apiRequest('/users/logout/', { method: 'POST' }) } finally { clearAccessToken() }
}

function publicPost(path, data) {
  return apiRequest(path, {
    method: 'POST', skipRefresh: true,
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
  })
}

export async function registerAccount(data) {
  const { user } = await publicPost('/users/register/', {
    ...data, username: data.username.trim(), email: data.email.trim(), full_name: data.full_name.trim(),
  })
  return user
}

export function requestPasswordReset(email) {
  return publicPost('/users/password-reset/', { email: email.trim() })
}

export function passwordResetPath(resetUrl) {
  const url = new URL(resetUrl, window.location.origin)
  const uid = url.searchParams.get('uid')
  const token = url.searchParams.get('token')
  if (!uid || !token || uid.length > 128 || token.length > 128) throw new Error('Invalid reset link')
  // Keep navigation on this frontend origin even if the backend uses localhost.
  return `/reset-password?${new URLSearchParams({ uid, token })}`
}

export async function confirmPasswordReset(data) {
  const result = await publicPost('/users/password-reset/confirm/', data)
  clearAccessToken()
  return result
}

export function accountFieldErrors(error) {
  if (error.status !== 400 || !error.data) return {}
  const messages = {
    username: 'Tên đăng nhập không hợp lệ hoặc đã được sử dụng.',
    email: 'Email không hợp lệ hoặc đã được sử dụng.',
    full_name: 'Vui lòng nhập họ và tên hợp lệ.',
    role: 'Vui lòng chọn Học viên hoặc Giáo viên.',
    password: PASSWORD_REQUIREMENTS,
    password_confirm: 'Mật khẩu xác nhận không khớp.',
    token: 'Liên kết không hợp lệ, đã hết hạn hoặc đã được sử dụng.',
    uid: 'Liên kết đặt lại mật khẩu không hợp lệ.',
  }
  return Object.fromEntries(Object.keys(error.data).filter((field) => messages[field]).map((field) => [field, messages[field]]))
}

export function accountErrorMessage(error) {
  if (error.status === 400) return 'Thông tin chưa hợp lệ. Vui lòng kiểm tra lại.'
  return authErrorMessage(error)
}

export function authErrorMessage(error) {
  if (error.status === 401) return 'Tên đăng nhập hoặc mật khẩu không đúng, hoặc tài khoản chưa được phép truy cập.'
  if (error.status === 403) return 'Bạn không có quyền thực hiện thao tác này.'
  if (error.status === 400) return 'Thông tin đăng nhập chưa hợp lệ. Vui lòng kiểm tra lại.'
  if (error.status === 429) return 'Có quá nhiều yêu cầu. Vui lòng chờ một lát rồi thử lại.'
  return 'Không thể kết nối với hệ thống. Vui lòng thử lại sau ít phút.'
}
