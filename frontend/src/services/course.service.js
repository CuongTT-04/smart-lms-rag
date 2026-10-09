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

export async function listAllEnrollmentRecords(path, signal) {
  const records = []
  let data
  let page = 1
  do {
    data = await apiRequest(`${path}${path.includes('?') ? '&' : '?'}page=${page}`, { signal })
    records.push(...resultsOf(data))
    page += 1
  } while (data?.next)
  return records
}

export const getAccessPolicy = (id, signal) => apiRequest(`/courses/${id}/access-policy/`, { signal })
export const updateAccessPolicy = (id, values) => writeRequest(`/courses/${id}/access-policy/`, 'PATCH', values)
export const listClassrooms = (id, signal) => listAllEnrollmentRecords(`/courses/${id}/classrooms/`, signal)
export const createClassroom = (id, values) => writeRequest(`/courses/${id}/classrooms/`, 'POST', values)
export const updateClassroom = (id, classroomId, values) => writeRequest(`/courses/${id}/classrooms/${classroomId}/`, 'PATCH', values)
export const listJoinRequests = (id, status = '', signal) => listAllEnrollmentRecords(`/courses/${id}/join-requests/${status ? `?status=${encodeURIComponent(status)}` : ''}`, signal)
export const reviewJoinRequest = (id, requestId, values) => writeRequest(`/courses/${id}/join-requests/${requestId}/review/`, 'POST', values)
export const joinClassroom = (values) => writeRequest('/courses/join/', 'POST', values)
export const listMyJoinRequests = (signal) => listAllEnrollmentRecords('/courses/join-requests/mine/', signal)
export const listMyEnrollments = (signal) => listAllEnrollmentRecords('/courses/enrollments/mine/', signal)
export const cancelJoinRequest = (id) => writeRequest(`/courses/join-requests/${id}/cancel/`, 'POST', {})
export const listClassroomEnrollments = (id, classroomId, status = '', signal) => listAllEnrollmentRecords(`/courses/${id}/classrooms/${classroomId}/enrollments/${status ? `?status=${encodeURIComponent(status)}` : ''}`, signal)
export const revokeClassroomEnrollment = (id, classroomId, enrollmentId) => writeRequest(`/courses/${id}/classrooms/${classroomId}/enrollments/${enrollmentId}/`, 'DELETE')
export const listMyCourseClassrooms = (id, signal) => listAllEnrollmentRecords(`/courses/${id}/my-classrooms/`, signal)

export function revokeStudentAccess(courseId, memberId) {
  return writeRequest(`/courses/${courseId}/members/${memberId}/`, 'DELETE')
}

export function resultsOf(data) {
  return Array.isArray(data) ? data : data?.results || []
}

export function courseErrorMessage(error) {
  if (error.status === 401) return 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.'
  if (error.status === 429) return 'Bạn đã gửi quá nhiều yêu cầu. Vui lòng thử lại sau.'
  if (error.status === 403) return 'Bạn không có quyền thực hiện thao tác này hoặc phiên đăng nhập đã hết hạn.'
  if (error.status === 404) return 'Không tìm thấy khóa học hoặc dữ liệu yêu cầu.'
  if (error.status === 400) {
    const data = error.data
    const messages = {
      'Invalid class code.': 'Mã lớp không đúng. Vui lòng kiểm tra lại với giáo viên.',
      'This classroom is not accepting enrollment.': 'Lớp hiện không nhận đăng ký hoặc khóa học chưa được xuất bản.',
      'Only free courses support joining by class code.': 'Chỉ khóa học miễn phí được tham gia bằng mã lớp.',
      'This request has already been processed.': 'Yêu cầu đã được xử lý. Vui lòng làm mới danh sách.',
      'Only pending requests can be canceled.': 'Chỉ có thể hủy yêu cầu đang chờ duyệt.',
      'The applicant is no longer an active student.': 'Tài khoản học viên hiện không còn đủ điều kiện tham gia.',
    }
    if (typeof data?.detail === 'string') return data.detail
    const first = data && Object.values(data).flat().find((message) => typeof message === 'string')
    return messages[first] || first || 'Dữ liệu chưa hợp lệ. Vui lòng kiểm tra lại.'
  }
  return 'Không thể kết nối với hệ thống. Vui lòng thử lại.'
}

export const listClassroomSessions = (id, roomId, signal) => listAllEnrollmentRecords(`/courses/${id}/classrooms/${roomId}/sessions/`, signal)
export const createClassroomSession = (id, roomId, values) => writeRequest(`/courses/${id}/classrooms/${roomId}/sessions/`, 'POST', values)

export const listClassroomAnnouncements = (id, roomId, signal) => listAllEnrollmentRecords(`/courses/${id}/classrooms/${roomId}/announcements/`, signal)
export function createClassroomAnnouncement(id, roomId, values) {
  const path = `/courses/${id}/classrooms/${roomId}/announcements/`
  if (!values.image) return writeRequest(path, 'POST', values)
  const body = new FormData()
  body.append('content', values.content)
  body.append('link', values.link || '')
  body.append('image', values.image)
  return apiRequest(path, { method: 'POST', body })
}
export const getAnnouncementImage = (id, roomId, announcementId, signal) => apiRequest(`/courses/${id}/classrooms/${roomId}/announcements/${announcementId}/image/`, { signal, responseType: 'image' })

export const updateClassroomSession = (id, roomId, sessionId, values) => writeRequest(`/courses/${id}/classrooms/${roomId}/sessions/${sessionId}/`, 'PATCH', values)
export const deleteClassroomSession = (id, roomId, sessionId) => writeRequest(`/courses/${id}/classrooms/${roomId}/sessions/${sessionId}/`, 'DELETE')
