import { apiRequest, clearAccessToken } from './api'
import { accountErrorMessage, accountFieldErrors } from './auth.service'

export async function updateProfile(changes) {
  const result = await apiRequest('/users/me/', {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes),
  })
  if (result.requires_login) clearAccessToken()
  return result
}

export async function uploadAvatar(file) {
  const body = new FormData()
  body.append('avatar', file)
  const { user } = await apiRequest('/users/me/avatar/', { method: 'POST', body })
  return user
}

export function profileErrors(error) {
  const fields = accountFieldErrors(error)
  const messages = {
    current_password: 'Mật khẩu hiện tại không đúng hoặc chưa được nhập.',
    phone: 'Số điện thoại cần 8–15 chữ số, có thể bắt đầu bằng dấu +.',
    avatar_url: 'Vui lòng nhập đường dẫn ảnh hợp lệ.',
    avatar: 'Ảnh cần là JPG, PNG hoặc WebP, tối đa 5 MB và 4096 pixel mỗi chiều.',
    learning_goal: 'Mục tiêu học tập không được vượt quá 5000 ký tự.',
    bio: 'Giới thiệu không được vượt quá 5000 ký tự.',
    specialization: 'Chuyên môn không được vượt quá 255 ký tự.',
  }
  if (error.status === 400) {
    for (const key of Object.keys(error.data || {})) {
      if (messages[key]) fields[key] = messages[key]
      if (['student_profile', 'teacher_profile'].includes(key)) {
        for (const nested of Object.keys(error.data[key] || {})) {
          if (messages[nested]) fields[nested] = messages[nested]
        }
      }
    }
  }
  return { fields, message: accountErrorMessage(error) }
}
