import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import StudentHomePage from './StudentHomePage'
import { getCourse, listAllCourses, listMyCourseClassrooms } from '../services/course.service'

vi.mock('../services/course.service', async (importOriginal) => ({
  ...await importOriginal(), getCourse: vi.fn(), listAllCourses: vi.fn(), listMyCourseClassrooms: vi.fn(),
}))

const student = { id: 'student-1', username: 'student_a', full_name: 'Nguyễn Minh Anh', email: 'student@example.com', role: 'STUDENT', status: 'ACTIVE' }
const course = { id: 'course-1', title: 'Lập trình Python căn bản', description: 'Nền tảng cho người mới bắt đầu', status: 'PUBLISHED', published_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-07T10:00:00Z' }

describe('student home', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    listAllCourses.mockResolvedValue([course])
    getCourse.mockResolvedValue(course)
  })

  it('shows enrolled courses in the student overview', async () => {
    render(<StudentHomePage user={student} onLogout={vi.fn()} />)
    expect(await screen.findByRole('heading', { name: 'Chào Anh!' })).toBeVisible()
    expect(screen.getByText('Lập trình Python căn bản')).toBeVisible()
    expect(screen.getByText('Khóa học của tôi', { selector: '.student-stat-card span' }).previousSibling).toHaveTextContent('1')
  })

  it('opens account management from the header dropdown', async () => {
    render(<StudentHomePage user={student} onLogout={vi.fn()} />)
    await screen.findByText('Lập trình Python căn bản')
    await userEvent.hover(screen.getByRole('button', { name: 'Xem hồ sơ của bạn' }))
    await userEvent.click(screen.getByRole('button', { name: 'Quản lý tài khoản' }))
    expect(screen.getByRole('heading', { name: 'Tài khoản của bạn' })).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Hồ sơ học viên' })).not.toBeInTheDocument()
  })

  it('filters courses in the course library', async () => {
    render(<StudentHomePage user={student} onLogout={vi.fn()} />)
    await screen.findByText('Lập trình Python căn bản')
    await userEvent.click(screen.getByRole('button', { name: 'Khóa học của tôi' }))
    await userEvent.type(screen.getByLabelText('Tìm khóa học'), 'Cơ sở dữ liệu')
    expect(screen.getByText('Không tìm thấy khóa học')).toBeVisible()
  })

  it('opens course information through the detail endpoint', async () => {
    render(<StudentHomePage user={student} onLogout={vi.fn()} />)
    await screen.findByText('Lập trình Python căn bản')
    await userEvent.click(screen.getByRole('button', { name: 'Khóa học của tôi' }))
    await userEvent.click(screen.getByRole('button', { name: 'Xem khóa học' }))
    expect(await screen.findByRole('heading', { name: 'Lập trình Python căn bản' })).toBeVisible()
    expect(getCourse).toHaveBeenCalledWith('course-1')
    await userEvent.click(screen.getByRole('button', { name: 'Quay lại danh sách' }))
    expect(await screen.findByRole('heading', { name: 'Khóa học của tôi' })).toBeVisible()
  })

  it('opens the account and logs out', async () => {
    const onLogout = vi.fn().mockResolvedValue(undefined)
    render(<StudentHomePage user={student} onLogout={onLogout} />)
    await screen.findByText('Lập trình Python căn bản')
    await userEvent.click(screen.getByRole('button', { name: 'Tài khoản', exact: true }))
    expect(await screen.findByRole('heading', { name: 'Tài khoản của bạn' })).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Đăng xuất khỏi OHAYO' }))
    expect(onLogout).toHaveBeenCalledTimes(1)
  })

  it('shows a recoverable API error', async () => {
    listAllCourses.mockRejectedValueOnce({ status: 0 })
    render(<StudentHomePage user={student} onLogout={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Không thể kết nối')
    await waitFor(() => expect(screen.getByText('Chưa có khóa học')).toBeVisible())
  })
  it('shows all enrolled classroom names on course cards and details', async () => {
    const my_classrooms = [
      { id: 'e1', classroom_name: 'Lớp buổi sáng', status: 'ACTIVE', progress_percent: 20, enrolled_at: '2026-10-08T10:00:00Z' },
      { id: 'e2', classroom_name: 'Lớp buổi tối', status: 'COMPLETED', progress_percent: 100, enrolled_at: '2026-10-08T10:00:00Z' },
    ]
    listAllCourses.mockResolvedValue([{ ...course, my_classrooms }])
    getCourse.mockResolvedValue({ ...course, my_classrooms })
    render(<StudentHomePage user={student} onLogout={vi.fn()} />)
    expect(await screen.findByText('Lớp buổi sáng')).toBeVisible()
    expect(screen.getByText('Lớp buổi tối')).toBeVisible()
    await userEvent.click(within(screen.getByText('Lớp buổi sáng').closest('article')).getByRole('button', { name: 'Xem khóa học', exact: true }))
    expect(await screen.findByRole('heading', { name: 'Lớp học của tôi' })).toBeVisible()
    const classrooms = screen.getByRole('region', { name: 'Lớp học của tôi' })
    expect(within(classrooms).getByText('Đang học')).toBeVisible()
    expect(within(classrooms).getByText('Đã hoàn thành')).toBeVisible()
    expect(screen.getAllByRole('progressbar')).toHaveLength(2)
  })
  it('returns to the course list when refreshing detects revoked access', async () => {
    listMyCourseClassrooms.mockRejectedValue({ status: 403 })
    render(<StudentHomePage user={student} onLogout={vi.fn()} />)
    await screen.findByText('Lập trình Python căn bản')
    await userEvent.click(screen.getByRole('button', { name: 'Khóa học của tôi' }))
    await userEvent.click(screen.getByRole('button', { name: 'Xem khóa học' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Làm mới lớp học của tôi' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('không có quyền')
    expect(screen.getByRole('heading', { name: 'Khóa học của tôi' })).toBeVisible()
    expect(screen.queryByText('Lập trình Python căn bản')).not.toBeInTheDocument()
  })
  it('preserves search and ignores a late detail response after going back', async () => {
    let resolveDetail
    getCourse.mockReturnValueOnce(new Promise((resolve) => { resolveDetail = resolve }))
    render(<StudentHomePage user={student} onLogout={vi.fn()} />)
    await screen.findByText(course.title)
    await userEvent.click(screen.getByRole('button', { name: 'Khóa học của tôi' }))
    await userEvent.type(screen.getByLabelText('Tìm khóa học'), 'Python')
    await userEvent.click(screen.getByRole('button', { name: 'Xem khóa học' }))
    await userEvent.click(screen.getByRole('button', { name: 'Quay lại danh sách' }))
    expect(screen.getByLabelText('Tìm khóa học')).toHaveValue('Python')
    resolveDetail(course)
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Lớp học của tôi' })).not.toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'Khóa học của tôi' })).toBeVisible()
  })
})
