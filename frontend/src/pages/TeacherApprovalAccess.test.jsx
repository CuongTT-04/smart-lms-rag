import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import TeacherHomePage from './TeacherHomePage'
import { TeacherEnrollmentPanel } from '../components/EnrollmentPanels'
import { currentUser, sendEmailVerification } from '../services/auth.service'
import { createClassroom, createCourse, listAllCourses, listAllCourseMembers, listClassrooms, listJoinRequests } from '../services/course.service'

vi.mock('../services/auth.service', async original => ({ ...await original(), currentUser: vi.fn(), sendEmailVerification: vi.fn() }))
vi.mock('../services/course.service', async original => ({ ...await original(), createClassroom: vi.fn(), createCourse: vi.fn(), listAllCourses: vi.fn(), listAllCourseMembers: vi.fn(), listClassrooms: vi.fn(), listJoinRequests: vi.fn() }))
const pending = { id: 'approval-teacher', role: 'TEACHER', status: 'ACTIVE', full_name: 'Giáo viên thử', username: 'teacher',
  email: 'teacher@example.com', teaching_allowed: false, email_verified: false, last_login: '2026-11-27T03:00:00Z',
  teacher_profile: { approval: { status: 'PENDING', revision: 1, source: '' } } }
const approved = { ...pending, teaching_allowed: true, teacher_profile: { approval: { status: 'APPROVED', revision: 2, source: 'ADMIN' } } }
const course = { id: 'approval-course', title: 'Khóa học riêng', status: 'DRAFT', description: '', updated_at: null }
beforeEach(() => {
  vi.clearAllMocks(); sessionStorage.clear()
  listAllCourses.mockResolvedValue([course]); listAllCourseMembers.mockResolvedValue([])
  listClassrooms.mockResolvedValue([]); listJoinRequests.mockResolvedValue([])
  currentUser.mockResolvedValue(pending)
})

it('blocks pending teacher actions, hides stale course data and explains disabled controls', async () => {
  render(<TeacherHomePage user={pending} />)
  expect(await screen.findByText('Tài khoản giáo viên đang chờ duyệt')).toBeVisible()
  const create = await screen.findByRole('button', { name: 'Tạo khóa học' })
  expect(create).toBeDisabled()
  expect(screen.queryByText('Khóa học riêng')).not.toBeInTheDocument()
  await userEvent.hover(create.parentElement)
  expect(screen.getByRole('tooltip')).toBeVisible()
  fireEvent.click(create)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(createCourse).not.toHaveBeenCalled()
})

it('dismisses only the current session/revision notice without restoring permissions', async () => {
  const view = render(<TeacherHomePage user={pending} />)
  await screen.findByRole('button', { name: 'Tạo khóa học' })
  await userEvent.click(screen.getByRole('button', { name: 'Ẩn thông báo xét duyệt' }))
  expect(screen.queryByText('Tài khoản giáo viên đang chờ duyệt')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Tạo khóa học' })).toBeDisabled()
  view.rerender(<TeacherHomePage user={{ ...pending, teacher_profile: { approval: { status: 'REVOKED', revision: 3 } } }} />)
  expect(await screen.findByText('Quyền giảng dạy đã bị thu hồi')).toBeVisible()
})

it('removes an already-open creation modal when approval changes', async () => {
  const view = render(<TeacherHomePage user={approved} />)
  await screen.findByText(course.title)
  await userEvent.click(within(screen.getByRole('navigation')).getByRole('button', { name: 'Khóa học', exact: true }))
  await userEvent.click(screen.getByRole('button', { name: 'Tạo khóa học' }))
  expect(screen.getByRole('dialog')).toBeVisible()
  view.rerender(<TeacherHomePage user={pending} />)
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(createCourse).not.toHaveBeenCalled()
})

it('refreshes from server after a denied request and fails closed while refreshing', async () => {
  const revoked = { ...pending, teacher_profile: { approval: { status: 'REVOKED', revision: 3 } } }
  currentUser.mockResolvedValue(revoked)
  render(<TeacherHomePage user={approved} />)
  await screen.findByText(course.title)
  act(() => window.dispatchEvent(new Event('ohayo:teaching-access-denied')))
  expect(await screen.findByText('Quyền giảng dạy đã bị thu hồi')).toBeVisible()
  expect(currentUser).toHaveBeenCalledTimes(1)
  expect(screen.queryByText(course.title)).not.toBeInTheDocument()
})

it('sends a verification request without granting teaching rights locally', async () => {
  sendEmailVerification.mockResolvedValue({ already_verified: false })
  render(<TeacherHomePage user={pending} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Gửi email xác minh' }))
  expect(await screen.findByText('Đã tiếp nhận yêu cầu. Vui lòng kiểm tra hộp thư.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Tạo khóa học' })).toBeDisabled()
})

it('keeps actions blocked if eligibility is missing or refresh fails', async () => {
  currentUser.mockRejectedValue({ status: 503 })
  render(<TeacherHomePage user={{ ...pending, teaching_allowed: undefined }} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Kiểm tra trạng thái' }))
  expect(await screen.findByText('Chưa kiểm tra được trạng thái. Vui lòng thử lại.')).toBeVisible()
  expect(screen.getByRole('button', { name: 'Tạo khóa học' })).toBeDisabled()
})

it('does not submit a classroom form outside an approved teaching context', async () => {
  render(<TeacherEnrollmentPanel course={course} />)
  const create = await screen.findByRole('button', { name: 'Tạo lớp' })
  expect(create).toBeDisabled()
  fireEvent.submit(create.closest('form'))
  await waitFor(() => expect(createClassroom).not.toHaveBeenCalled())
})
