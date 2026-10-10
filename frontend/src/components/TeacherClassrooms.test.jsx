import { expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TeacherClassrooms from './TeacherClassrooms'
vi.mock('../services/course.service', async (original) => ({ ...await original(), listClassrooms: vi.fn(async () => [{ id: 'r1', name: 'Lớp sáng', class_code: 'ABCDEF123456', enrolled_count: 2, is_join_enabled: true }]) }))
it('opens the class when its footer is clicked and supports keyboard activation', async () => {
  const course = { id: 'c1', title: 'Python' }
  const open = vi.fn()
  render(<TeacherClassrooms courses={[course]} onOpen={open} />)
  await screen.findByRole('button', { name: 'Mở lớp Lớp sáng' })
  await userEvent.click(screen.getByText('ABCDEF123456'))
  expect(open).toHaveBeenCalledWith(course, expect.objectContaining({ id: 'r1' }))
  expect(screen.queryByRole('button', { name: 'Quản lý khóa học' })).not.toBeInTheDocument()
  open.mockClear()
  screen.getByRole('button', { name: 'Mở lớp Lớp sáng' }).focus()
  await userEvent.keyboard('{Enter}')
  expect(open).toHaveBeenCalledTimes(1)
  await userEvent.keyboard(' ')
  expect(open).toHaveBeenCalledTimes(2)
})
