import { apiRequest } from './api'

function writeRequest(path, method, body) {
  return apiRequest(path, {
    method,
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
}

export function listCourses(page = 1, signal) {
  return apiRequest(`/courses/?page=${page}`, { signal })
}

export async function listAllCourses(signal) {
  let page = 1
  let data
  const courses = []
  do {
    data = await listCourses(page, signal)
    courses.push(...resultsOf(data))
    page += 1
  } while (data?.next)
  return courses
}

export function getCourse(courseId, signal) {
  return apiRequest(`/courses/${courseId}/`, { signal })
}

export function createCourse(values) {
  return writeRequest('/courses/', 'POST', values)
}

export function updateCourse(courseId, values) {
  return writeRequest(`/courses/${courseId}/`, 'PATCH', values)
}

export function listCourseMembers(courseId, page = 1, signal) {
  return apiRequest(`/courses/${courseId}/members/?page=${page}`, { signal })
}

export async function listAllCourseMembers(courseId, signal) {
  let page = 1
  let data
  const members = []
  do {
    data = await listCourseMembers(courseId, page, signal)
    members.push(...resultsOf(data))
    page += 1
  } while (data?.next)
  return members
}

export function grantStudentAccess(courseId, userId) {
  return writeRequest(`/courses/${courseId}/members/`, 'POST', { user_id: userId })
}

export function revokeStudentAccess(courseId, memberId) {
  return writeRequest(`/courses/${courseId}/members/${memberId}/`, 'DELETE')
}

export function resultsOf(data) {
  return Array.isArray(data) ? data : data?.results || []
}

export function courseErrorMessage(error) {
  if (error.status === 403) return 'Bạn không có quyền thực hiện thao tác này hoặc phiên đăng nhập đã hết hạn.'
  if (error.status === 404) return 'Không tìm thấy khóa học hoặc dữ liệu yêu cầu.'
  if (error.status === 400) {
    const data = error.data
    if (typeof data?.detail === 'string') return data.detail
    const first = data && Object.values(data).flat().find((message) => typeof message === 'string')
    return first || 'Dữ liệu chưa hợp lệ. Vui lòng kiểm tra lại.'
  }
  return 'Không thể kết nối với hệ thống. Vui lòng thử lại.'
}
