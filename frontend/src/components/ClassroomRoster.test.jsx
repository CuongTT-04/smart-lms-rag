import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ClassroomRoster from './ClassroomRoster'
import { listClassroomEnrollments, revokeClassroomEnrollment } from '../services/course.service'

vi.mock('../services/course.service', async (original) => ({
  ...await original(), listClassroomEnrollments: vi.fn(), revokeClassroomEnrollment: vi.fn(),
}))
const course = { id: 'c1', title: 'Python' }
const room = { id: 'room1', name: 'Lớp tối' }
const record = { id: 'enrollment1', status: 'ACTIVE', progress_percent: 25, enrolled_at: '2026-10-08T10:00:00Z', student: { id: 'student1', full_name: 'Nguyễn Minh Anh', username: 'anh', email: 'anh@example.com' } }

describe('classroom roster', () => {
  beforeEach(() => { vi.resetAllMocks(); listClassroomEnrollments.mockResolvedValue([record]) })
  const renderRoster = (onMembersChanged = vi.fn()) => render(<ClassroomRoster course={course} room={room} onBack={vi.fn()} onMembersChanged={onMembersChanged} />)

  it('loads the selected classroom and filters by enrollment status', async () => {
    renderRoster()
    expect(await screen.findByText('Nguyễn Minh Anh')).toBeVisible()
    expect(listClassroomEnrollments).toHaveBeenCalledWith('c1', 'room1', 'ACTIVE', expect.any(AbortSignal))
    listClassroomEnrollments.mockResolvedValue([{ ...record, status: 'WITHDRAWN' }])
    await userEvent.click(screen.getByRole('button', { name: 'Đã thu hồi', exact: true }))
    await screen.findByText('Nguyễn Minh Anh')
    expect(listClassroomEnrollments).toHaveBeenLastCalledWith('c1', 'room1', 'WITHDRAWN', expect.any(AbortSignal))
    expect(screen.queryByRole('button', { name: /Thu hồi ghi danh/ })).not.toBeInTheDocument()
  })
  it('searches students by email', async () => {
    renderRoster()
    await screen.findByText('Nguyễn Minh Anh')
    await userEvent.type(screen.getByLabelText('Tìm học viên trong lớp'), 'unknown@example.com')
    expect(screen.getByText('Không tìm thấy học viên phù hợp.')).toBeVisible()
    await userEvent.clear(screen.getByLabelText('Tìm học viên trong lớp'))
    await userEvent.type(screen.getByLabelText('Tìm học viên trong lớp'), 'anh@example.com')
    expect(screen.getByText('Nguyễn Minh Anh')).toBeVisible()
  })
  it('requires confirmation and uses the enrollment id rather than student id', async () => {
    const changed = vi.fn()
    renderRoster(changed)
    await userEvent.click(await screen.findByRole('button', { name: 'Thu hồi ghi danh của Nguyễn Minh Anh' }))
    const dialog = screen.getByRole('dialog', { name: 'Thu hồi ghi danh ở lớp?' })
    expect(within(dialog).getByText(/Các lớp khác không bị thu hồi/)).toBeVisible()
    expect(revokeClassroomEnrollment).not.toHaveBeenCalled()
    listClassroomEnrollments.mockResolvedValue([])
    await userEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận thu hồi' }))
    expect(revokeClassroomEnrollment).toHaveBeenCalledWith('c1', 'room1', 'enrollment1')
    expect(await screen.findByRole('status')).toHaveTextContent('Đã thu hồi ghi danh')
    await waitFor(() => expect(changed).toHaveBeenCalled())
    expect(screen.queryByText('Nguyễn Minh Anh', { selector: 'strong' })).not.toBeInTheDocument()
  })
  it('cancels confirmation without a request', async () => {
    renderRoster()
    await userEvent.click(await screen.findByRole('button', { name: /Thu hồi ghi danh/ }))
    await userEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Hủy' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(revokeClassroomEnrollment).not.toHaveBeenCalled()
  })
  it('reports forbidden withdrawal without changing the roster', async () => {
    revokeClassroomEnrollment.mockRejectedValue({ status: 403 })
    renderRoster()
    await userEvent.click(await screen.findByRole('button', { name: /Thu hồi ghi danh/ }))
    await userEvent.click(screen.getByRole('button', { name: 'Xác nhận thu hồi' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('không có quyền')
    expect(screen.getByText('Nguyễn Minh Anh')).toBeVisible()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
  it('does not show a withdrawn record as active when reloading fails', async () => {
    renderRoster()
    await userEvent.click(await screen.findByRole('button', { name: /Thu hồi ghi danh/ }))
    listClassroomEnrollments.mockRejectedValue({ status: 0 })
    await userEvent.click(screen.getByRole('button', { name: 'Xác nhận thu hồi' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Đã thu hồi thành công')
    expect(screen.queryByRole('button', { name: /Thu hồi ghi danh/ })).not.toBeInTheDocument()
  })
  it('supports retry after an initial loading error', async () => {
    listClassroomEnrollments.mockRejectedValueOnce({ status: 404 })
    renderRoster()
    expect(await screen.findByRole('alert')).toHaveTextContent('Không tìm thấy')
    await userEvent.click(screen.getByRole('button', { name: 'Làm mới học viên của lớp' }))
    expect(await screen.findByText('Nguyễn Minh Anh')).toBeVisible()
  })
})
