import { expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import StudentClassroomPeople from './StudentClassroomPeople'
vi.mock('../services/course.service', () => ({ courseErrorMessage: () => 'Không thể tải danh sách.', listClassroomPeople: vi.fn(async () => ({ owners:[{id:'o1',name:'Giáo viên A'}], students:[{id:'s1',name:'Học sinh B'}] })) }))
it('shows the owner separately before the students', async () => {
  render(<StudentClassroomPeople courseId="c1" roomId="r1" />)
  const owners = await screen.findByRole('region',{name:'Giáo viên phụ trách'})
  expect(within(owners).getByText('Giáo viên A')).toBeVisible()
  expect(within(owners).getByText('Chủ lớp')).toBeVisible()
  expect(within(screen.getByRole('region',{name:'Học viên'})).getByText('Học sinh B')).toBeVisible()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})
