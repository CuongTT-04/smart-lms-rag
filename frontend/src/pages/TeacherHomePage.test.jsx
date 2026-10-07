import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TeacherHomePage from './TeacherHomePage'
import {
  createCourse, grantStudentAccess, listAllCourseMembers, listAllCourses,
  revokeStudentAccess, updateCourse,
} from '../services/course.service'

vi.mock('../services/course.service', async (importOriginal) => ({
  ...await importOriginal(),
  createCourse: vi.fn(), grantStudentAccess: vi.fn(), listAllCourseMembers: vi.fn(),
  listAllCourses: vi.fn(), revokeStudentAccess: vi.fn(), updateCourse: vi.fn(),
}))

const teacher = { id: 'teacher-1', username: 'teacher_a', full_name: 'Nguyễn Minh Giáo', email: 'teacher@example.com', role: 'TEACHER', status: 'ACTIVE' }
const course = { id: 'course-1', title: 'Lập trình Python', description: 'Khóa học nền tảng', status: 'PUBLISHED', updated_at: '2026-10-07T10:00:00Z' }
const owner = { id: 'owner-1', role: 'OWNER', status: 'ACTIVE', user: teacher }
const student = { id: 'member-1', role: 'STUDENT', status: 'ACTIVE', user: { id: 'student-1', username: 'student_a', full_name: 'Nguyễn Minh Anh', email: 'student@example.com' } }

describe('teacher home', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listAllCourses.mockResolvedValue([course])
    listAllCourseMembers.mockResolvedValue([owner, student])
  })

  it('shows teacher dashboard statistics and recent courses', async () => {
    render(<TeacherHomePage user={teacher} onLogout={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: 'Xin chào, Nguyễn Minh Giáo!' })).toBeVisible()
    expect(screen.getByText('Lập trình Python')).toBeVisible()
    expect(screen.getByText('1 học viên')).toBeVisible()
    expect(screen.getByText('Tổng khóa học').previousSibling).toHaveTextContent('1')
  })

  it('replaces the header create button with an avatar and account dropdown', async () => {
    render(<TeacherHomePage user={teacher} onLogout={vi.fn()} />)
    await screen.findByText('Lập trình Python')
    const header = screen.getByRole('button', { name: 'Xem hồ sơ của bạn' }).closest('header')
    expect(within(header).queryByRole('button', { name: 'Tạo khóa học' })).not.toBeInTheDocument()
    await userEvent.hover(within(header).getByRole('button', { name: 'Xem hồ sơ của bạn' }))
    await userEvent.click(screen.getByRole('button', { name: 'Quản lý tài khoản' }))
    expect(screen.getByRole('heading', { name: 'Tài khoản của bạn' })).toBeVisible()
  })

  it('creates a draft course and opens its management screen', async () => {
    const newCourse = { ...course, id: 'course-2', title: 'Cơ sở dữ liệu', status: 'DRAFT' }
    createCourse.mockResolvedValueOnce(newCourse)
    render(<TeacherHomePage user={teacher} onLogout={vi.fn()} />)
    await screen.findByText('Lập trình Python')
    await userEvent.click(screen.getAllByRole('button', { name: 'Tạo khóa học' })[0])
    const dialog = screen.getByRole('dialog', { name: 'Tạo khóa học mới' })
    await userEvent.type(within(dialog).getByLabelText(/Tên khóa học/), 'Cơ sở dữ liệu')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Tạo khóa học' }))
    expect(createCourse).toHaveBeenCalledWith({ title: 'Cơ sở dữ liệu', description: '' })
    expect(await screen.findByRole('heading', { name: 'Cơ sở dữ liệu' })).toBeVisible()
  })

  it('updates course status and information', async () => {
    const updated = { ...course, status: 'ARCHIVED', title: 'Python nâng cao' }
    updateCourse.mockResolvedValueOnce(updated)
    render(<TeacherHomePage user={teacher} onLogout={vi.fn()} />)
    await screen.findByText('Lập trình Python')
    await userEvent.click(screen.getByRole('button', { name: /Quản lý/ }))
    const title = screen.getByLabelText('Tên khóa học')
    await userEvent.clear(title)
    await userEvent.type(title, 'Python nâng cao')
    await userEvent.selectOptions(screen.getByLabelText('Trạng thái'), 'ARCHIVED')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }))
    expect(updateCourse).toHaveBeenCalledWith('course-1', expect.objectContaining({ title: 'Python nâng cao', status: 'ARCHIVED' }))
    expect(await screen.findByText('Đã cập nhật khóa học.')).toBeVisible()
  })

  it('grants and revokes student access', async () => {
    grantStudentAccess.mockResolvedValueOnce(student)
    revokeStudentAccess.mockResolvedValueOnce(undefined)
    render(<TeacherHomePage user={teacher} onLogout={vi.fn()} />)
    await screen.findByText('Lập trình Python')
    await userEvent.click(screen.getByRole('button', { name: /Quản lý/ }))
    await userEvent.click(screen.getByRole('button', { name: /Thành viên/ }))
    await userEvent.type(screen.getByLabelText('UUID học viên'), '11111111-1111-4111-8111-111111111111')
    await userEvent.click(screen.getByRole('button', { name: 'Thêm' }))
    expect(grantStudentAccess).toHaveBeenCalledWith('course-1', '11111111-1111-4111-8111-111111111111')
    await waitFor(() => expect(listAllCourseMembers).toHaveBeenCalledTimes(2))
    await userEvent.click(screen.getByRole('button', { name: 'Thu hồi' }))
    expect(revokeStudentAccess).toHaveBeenCalledWith('course-1', 'member-1')
  })

  it('logs out from the profile control', async () => {
    const onLogout = vi.fn().mockResolvedValue(undefined)
    render(<TeacherHomePage user={teacher} onLogout={onLogout} />)
    await screen.findByText('Lập trình Python')
    await userEvent.click(screen.getByRole('button', { name: 'Đăng xuất' }))
    expect(onLogout).toHaveBeenCalledTimes(1)
  })
})
