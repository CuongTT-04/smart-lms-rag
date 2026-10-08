import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  courseErrorMessage, createCourse, joinClassroom, listCourseMembers,
  listCourses, resultsOf, revokeStudentAccess, updateCourse, listClassrooms,
  listJoinRequests, listMyJoinRequests, listMyEnrollments, cancelJoinRequest,
  reviewJoinRequest, createClassroom, updateClassroom, updateAccessPolicy,
  listClassroomEnrollments, revokeClassroomEnrollment, listMyCourseClassrooms,
} from './course.service'

const json = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

describe('course service', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()))
  afterEach(() => vi.unstubAllGlobals())

  it('lists paginated courses using the bearer-capable API client', async () => {
    fetch.mockResolvedValueOnce(json({ count: 1, results: [{ id: 'course-1' }] }))
    expect(resultsOf(await listCourses())).toEqual([{ id: 'course-1' }])
    expect(fetch).toHaveBeenCalledWith('/api/courses/?page=1', expect.objectContaining({ credentials: 'include' }))
  })

  it('creates a course without a CSRF bootstrap request', async () => {
    fetch.mockResolvedValueOnce(json({ id: 'course-1', title: 'Python' }, 201))
    await createCourse({ title: 'Python', description: '' })
    expect(fetch).toHaveBeenCalledWith('/api/courses/', expect.objectContaining({
      method: 'POST', headers: expect.not.objectContaining({ 'X-CSRFToken': expect.anything() }),
      body: JSON.stringify({ title: 'Python', description: '' }),
    }))
  })

  it('updates course information with PATCH', async () => {
    fetch.mockResolvedValueOnce(json({ id: 'course-1', status: 'PUBLISHED' }))
    await updateCourse('course-1', { status: 'PUBLISHED' })
    expect(fetch).toHaveBeenCalledWith('/api/courses/course-1/', expect.objectContaining({ method: 'PATCH' }))
  })

  it('lists members, joins by code and revokes access', async () => {
    fetch.mockResolvedValueOnce(json({ results: [{ id: 'member-1' }] }))
    expect(resultsOf(await listCourseMembers('course-1'))).toHaveLength(1)
    fetch.mockResolvedValueOnce(json({ id: 'member-2' }, 201))
    await joinClassroom({ class_code: 'A1B2C3D4E5F6', message: '' })
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/courses/join/', expect.objectContaining({ body: JSON.stringify({ class_code: 'A1B2C3D4E5F6', message: '' }) }))
    fetch.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await revokeStudentAccess('course-1', 'member-2')
    expect(fetch).toHaveBeenNthCalledWith(3, '/api/courses/course-1/members/member-2/', expect.objectContaining({ method: 'DELETE' }))
  })

  it('translates common API failures', () => {
    expect(courseErrorMessage({ status: 403 })).toContain('không có quyền')
    expect(courseErrorMessage({ status: 404 })).toContain('Không tìm thấy')
    expect(courseErrorMessage({ status: 400, data: { title: ['Tên khóa học không hợp lệ.'] } })).toBe('Tên khóa học không hợp lệ.')
    expect(courseErrorMessage({ status: 0 })).toContain('Không thể kết nối')
    expect(courseErrorMessage({ status: 429 })).toContain('quá nhiều')
  })
  it('fetches every page of classrooms', async () => {
    fetch.mockResolvedValueOnce(json({ next: '/api/courses/c1/classrooms/?page=2', results: [{ id: 'room1' }] }))
    fetch.mockResolvedValueOnce(json({ next: null, results: [{ id: 'room2' }] }))
    expect(await listClassrooms('c1')).toEqual([{ id: 'room1' }, { id: 'room2' }])
    expect(fetch).toHaveBeenLastCalledWith('/api/courses/c1/classrooms/?page=2', expect.anything())
  })
  it('uses enrollment endpoints and only sends accepted fields', async () => {
    fetch.mockImplementation(async () => json({ results: [], next: null }))
    await listJoinRequests('c1', 'PENDING')
    await listMyJoinRequests()
    await listMyEnrollments()
    await cancelJoinRequest('r1')
    await reviewJoinRequest('c1', 'r1', { decision: 'reject', review_note: '' })
    await createClassroom('c1', { name: 'Lớp mới' })
    await updateClassroom('c1', 'room1', { is_join_enabled: false })
    await updateAccessPolicy('c1', { require_approval: true })
    expect(fetch.mock.calls.map(([path]) => path)).toEqual([
      '/api/courses/c1/join-requests/?status=PENDING&page=1',
      '/api/courses/join-requests/mine/?page=1', '/api/courses/enrollments/mine/?page=1',
      '/api/courses/join-requests/r1/cancel/', '/api/courses/c1/join-requests/r1/review/',
      '/api/courses/c1/classrooms/', '/api/courses/c1/classrooms/room1/', '/api/courses/c1/access-policy/',
    ])
    expect(fetch.mock.calls[3][1]).toEqual(expect.objectContaining({ method: 'POST', body: '{}' }))
  })
  it('fetches the entire class roster with a status filter', async () => {
    fetch.mockResolvedValueOnce(json({ next: '?page=2', results: [{ id: 'e1' }] }))
    fetch.mockResolvedValueOnce(json({ next: null, results: [{ id: 'e2' }] }))
    expect(await listClassroomEnrollments('c1', 'room1', 'ACTIVE')).toEqual([{ id: 'e1' }, { id: 'e2' }])
    expect(fetch.mock.calls.map(([path]) => path)).toEqual([
      '/api/courses/c1/classrooms/room1/enrollments/?status=ACTIVE&page=1',
      '/api/courses/c1/classrooms/room1/enrollments/?status=ACTIVE&page=2',
    ])
  })
  it('withdraws by enrollment id with no body and lists own course classes', async () => {
    fetch.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await revokeClassroomEnrollment('c1', 'room1', 'e1')
    expect(fetch).toHaveBeenCalledWith('/api/courses/c1/classrooms/room1/enrollments/e1/', expect.objectContaining({ method: 'DELETE' }))
    expect(fetch.mock.calls[0][1]).not.toHaveProperty('body')
    fetch.mockResolvedValueOnce(json({ next: null, results: [{ id: 'e2' }] }))
    expect(await listMyCourseClassrooms('c1')).toEqual([{ id: 'e2' }])
    expect(fetch).toHaveBeenLastCalledWith('/api/courses/c1/my-classrooms/?page=1', expect.anything())
  })
})
