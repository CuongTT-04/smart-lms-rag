import { apiRequest } from '../../services/api'

export async function adminRequest(path, options) {
  try { return await apiRequest(`/operations/${path}`, options) } catch (error) {
    if (error.status === 401) window.dispatchEvent(new Event('ohayo:session-expired'))
    if (error.status === 403 && path !== 'capabilities/') window.dispatchEvent(new Event('ohayo:admin-permissions-changed'))
    throw error
  }
}
export const writeAdmin = (path, body, method = 'POST') => adminRequest(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
export function adminError(error) {
  if (error?.status === 409) return typeof error.data?.message === 'string' ? error.data.message : 'Dữ liệu đã thay đổi hoặc thao tác chưa đủ điều kiện. Hãy tải lại hồ sơ để kiểm tra.'
  if (error?.status === 403) return 'Bạn chưa có quyền này hoặc mật khẩu xác nhận chưa đúng.'
  if (error?.status === 429) return 'Bạn thao tác quá nhanh. Vui lòng đợi một phút rồi thử lại.'
  if (error?.status === 400) {
    const data = error.data
    return Object.entries(data || {}).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(' ') : String(value)}`).join(' · ') || 'Vui lòng kiểm tra các trường đã nhập.'
  }
  return 'Chưa kết nối được dữ liệu. Vui lòng thử lại.'
}
