import { expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TeacherEnrollmentPanel } from './EnrollmentPanels'
import * as service from '../services/course.service'
vi.mock('../services/course.service', async (original) => ({ ...await original(), getAccessPolicy: vi.fn(), listClassrooms: vi.fn(), listJoinRequests: vi.fn(), updateClassroom: vi.fn() }))
it('edits one class independently and keeps the draft when saving fails', async () => {
  const room = { id: 'r1', name: 'Lớp một', class_code: 'ABCDEF123456', visibility: 'PRIVATE', require_approval: false, is_join_enabled: true }
  service.getAccessPolicy.mockResolvedValue({ visibility: 'PRIVATE', require_approval: false })
  service.listClassrooms.mockResolvedValue([room, { ...room, id: 'r2', name: 'Lớp hai' }])
  service.listJoinRequests.mockResolvedValue([])
  service.updateClassroom.mockRejectedValueOnce({ status: 0 }).mockResolvedValueOnce({ ...room, name: 'Tên mới', require_approval: true, is_join_enabled: false })
  render(<TeacherEnrollmentPanel course={{ id: 'c1', status: 'PUBLISHED' }} onMembersChanged={vi.fn()} />)
  await screen.findByText('Lớp một')
  expect(screen.queryByRole('textbox', { name: 'Tên lớp Lớp một' })).not.toBeInTheDocument()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Chỉnh sửa lớp Lớp một' }))
  const dialog = within(screen.getByRole('dialog'))
  await userEvent.clear(dialog.getByLabelText('Tên lớp'))
  await userEvent.type(dialog.getByLabelText('Tên lớp'), 'Tên mới')
  await userEvent.selectOptions(dialog.getByLabelText('Mức hiển thị'), 'PUBLIC')
  await userEvent.click(dialog.getByLabelText('Yêu cầu giáo viên xét duyệt'))
  await userEvent.click(dialog.getByLabelText('Mở đăng ký'))
  await userEvent.click(dialog.getByRole('button', { name: 'Lưu chỉnh sửa' }))
  expect(await dialog.findByRole('alert')).toBeVisible()
  expect(dialog.getByLabelText('Tên lớp')).toHaveValue('Tên mới')
  await userEvent.click(dialog.getByRole('button', { name: 'Lưu chỉnh sửa' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(service.updateClassroom).toHaveBeenLastCalledWith('c1', 'r1', { name: 'Tên mới', visibility: 'PUBLIC', require_approval: true, is_join_enabled: false })
  expect(screen.getByText('Lớp hai')).toBeVisible()
})

it('cancels with Escape and restores focus without writing', async () => {
  service.listClassrooms.mockResolvedValue([{ id: 'r1', name: 'Lớp một', class_code: 'ABCDEF123456', visibility: 'PRIVATE', require_approval: false, is_join_enabled: true }])
  service.listJoinRequests.mockResolvedValue([])
  service.updateClassroom.mockClear()
  render(<TeacherEnrollmentPanel course={{ id: 'c1', status: 'PUBLISHED' }} />)
  const edit = await screen.findByRole('button', { name: 'Chỉnh sửa lớp Lớp một' })
  await userEvent.click(edit)
  expect(screen.getByLabelText('Tên lớp')).toHaveFocus()
  await userEvent.keyboard('{Escape}')
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(edit).toHaveFocus()
  expect(service.updateClassroom).not.toHaveBeenCalled()
})
