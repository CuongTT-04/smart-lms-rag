import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TeacherHomePage from './TeacherHomePage'
import {
  createCourse, listAllCourseMembers, listAllCourses,
  revokeStudentAccess, updateCourse,
} from '../services/course.service'

vi.mock('../services/course.service', async (importOriginal) => ({
  ...await importOriginal(),
  createCourse: vi.fn(), listAllCourseMembers: vi.fn(),
  listAllCourses: vi.fn(), revokeStudentAccess: vi.fn(), updateCourse: vi.fn(),
}))

const teacher = { id: 'teacher-1', username: 'teacher_a', full_name: 'Nguyễn Minh Giáo', email: 'teacher@example.com', role: 'TEACHER', status: 'ACTIVE' }
const course = { id: 'course-1', title: 'Lập trình Python', description: 'Khóa học nền tảng', status: 'PUBLISHED', updated_at: '2026-10-07T10:00:00Z' }
const owner = { id: 'owner-1', role: 'OWNER', status: 'ACTIVE', user: teacher }
const student = { id: 'member-1', role: 'STUDENT', status: 'ACTIVE', user: { id: 'student-1', username: 'student_a', full_name: 'Nguyễn Minh Anh', email: 'student@example.com' } }

describe('teacher home', () => {
  it('restores the course list and detail with browser Back and Forward', async () => {
    render(<TeacherHomePage user={teacher} onLogout={vi.fn()} />)
    await screen.findByText('Lập trình Python')
    await userEvent.click(within(screen.getByRole('navigation', { name: 'Điều hướng giáo viên' })).getByRole('button', { name: 'Khóa học', exact: true }))
    await userEvent.click(screen.getByText('Lập trình Python'))
    expect(await screen.findByLabelText('Tên khóa học')).toBeVisible()
    act(() => window.history.back())
    await waitFor(() => expect(screen.queryByLabelText('Tên khóa học')).not.toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'Khóa học của tôi' })).toBeVisible()
    act(() => window.history.forward())
    expect(await screen.findByLabelText('Tên khóa học')).toHaveValue('Lập trình Python')
  })
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
    await userEvent.click(within(screen.getByRole('navigation', {name:'Điều hướng giáo viên'})).getByRole('button', {name:'Khóa học', exact:true}))
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
    await userEvent.click(screen.getByRole('combobox', { name: 'Trạng thái' }))
    await userEvent.click(screen.getByRole('option', { name: 'Đã lưu trữ' }))
    await userEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }))
    expect(updateCourse).toHaveBeenCalledWith('course-1', expect.objectContaining({ title: 'Python nâng cao', status: 'ARCHIVED' }))
    expect(await screen.findByText('Đã cập nhật khóa học.')).toBeVisible()
  })

  it.each(['Lập trình Python', '1 học viên'])('opens course management by clicking the card content: %s', async (label) => {
    render(<TeacherHomePage user={teacher} onLogout={vi.fn()} />)
    await screen.findByText('Lập trình Python')
    await userEvent.click(within(screen.getByRole('navigation', { name: 'Điều hướng giáo viên' })).getByRole('button', { name: 'Khóa học', exact: true }))
    await userEvent.click(screen.getByText(label))
    expect(await screen.findByLabelText('Tên khóa học')).toHaveValue('Lập trình Python')
  })

  it('opens a course card with the keyboard', async () => {
    const user = userEvent.setup()
    render(<TeacherHomePage user={teacher} onLogout={vi.fn()} />)
    await screen.findByText('Lập trình Python')
    const open = screen.getByRole('button', { name: /Quản lý/ })
    open.focus()
    await user.keyboard('{Enter}')
    expect(await screen.findByLabelText('Tên khóa học')).toHaveValue('Lập trình Python')
  })

  it.each(['Tổng quan', 'Khóa học'])('opens a course from the empty card area in %s', async (page) => {
    render(<TeacherHomePage user={teacher} onLogout={vi.fn()} />)
    await screen.findByText('Lập trình Python')
    await userEvent.click(within(screen.getByRole('navigation', { name: 'Điều hướng giáo viên' })).getByRole('button', { name: page, exact: true }))
    const card = screen.getByRole('heading', { name: 'Lập trình Python' }).closest('article')
    await userEvent.click(card)
    expect(await screen.findByLabelText('Tên khóa học')).toHaveValue('Lập trình Python')
  })

  it('removes direct grants and retains student revocation', async () => {
    revokeStudentAccess.mockResolvedValueOnce(undefined)
    render(<TeacherHomePage user={teacher} onLogout={vi.fn()} />)
    await screen.findByText('Lập trình Python')
    await userEvent.click(screen.getByRole('button', { name: /Quản lý/ }))
    await userEvent.click(screen.getByRole('button', { name: /Thành viên/ }))
    expect(screen.queryByLabelText('UUID học viên')).not.toBeInTheDocument()
    expect(within(screen.getByRole('region', { name: 'Lập trình Python' })).getByRole('button', { name: 'Lớp học' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Yêu cầu tham gia' })).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Thu hồi cả khóa' }))
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
