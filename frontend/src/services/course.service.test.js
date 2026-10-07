import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  courseErrorMessage, createCourse, grantStudentAccess, listCourseMembers,
  listCourses, resultsOf, revokeStudentAccess, updateCourse,
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

  it('lists, grants and revokes course members', async () => {
    fetch.mockResolvedValueOnce(json({ results: [{ id: 'member-1' }] }))
    expect(resultsOf(await listCourseMembers('course-1'))).toHaveLength(1)
    fetch.mockResolvedValueOnce(json({ id: 'member-2' }, 201))
    await grantStudentAccess('course-1', 'user-1')
    expect(fetch).toHaveBeenNthCalledWith(2, '/api/courses/course-1/members/', expect.objectContaining({ body: JSON.stringify({ user_id: 'user-1' }) }))
    fetch.mockResolvedValueOnce(new Response(null, { status: 204 }))
    await revokeStudentAccess('course-1', 'member-2')
    expect(fetch).toHaveBeenNthCalledWith(3, '/api/courses/course-1/members/member-2/', expect.objectContaining({ method: 'DELETE' }))
  })

  it('translates common API failures', () => {
    expect(courseErrorMessage({ status: 403 })).toContain('không có quyền')
    expect(courseErrorMessage({ status: 404 })).toContain('Không tìm thấy')
    expect(courseErrorMessage({ status: 400, data: { title: ['Tên khóa học không hợp lệ.'] } })).toBe('Tên khóa học không hợp lệ.')
    expect(courseErrorMessage({ status: 0 })).toContain('Không thể kết nối')
  })
})
