import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import StudentCoursesView from './StudentCoursesView'

const course = { id: 'c1', title: 'Python', description: 'Nền tảng lập trình', updated_at: '2026-10-08T10:00:00Z', my_classrooms: [{ id: 'e1', classroom_name: 'Lớp buổi tối', status: 'ACTIVE' }] }
function Harness(props) {
  const [search, setSearch] = useState('')
  return <StudentCoursesView courses={[course]} onOpen={vi.fn()} onRefresh={vi.fn()} onJoin={vi.fn()} {...props} search={search} setSearch={setSearch} />
}
describe('student course library', () => {
  it('searches classroom names as well as course titles and clears filters', async () => {
    render(<Harness />)
    await userEvent.type(screen.getByLabelText('Tìm khóa học'), 'buổi tối')
    expect(screen.getByRole('heading', { name: 'Python' })).toBeVisible()
    await userEvent.type(screen.getByLabelText('Tìm khóa học'), 'không tồn tại')
    expect(screen.getByText('Không tìm thấy khóa học')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Xóa bộ lọc' }))
    expect(screen.getByRole('heading', { name: 'Python' })).toBeVisible()
  })
  it('only marks courses completed when all their classes are completed', async () => {
    const completed = { ...course, id: 'c2', title: 'SQL', my_classrooms: [{ id: 'e2', classroom_name: 'Lớp SQL', status: 'COMPLETED' }] }
    const mixed = { ...course, id: 'c3', title: 'React', my_classrooms: [...course.my_classrooms, ...completed.my_classrooms] }
    render(<Harness courses={[course, completed, mixed, { ...course, id: 'c4', title: 'Java', my_classrooms: [] }]} />)
    await userEvent.click(screen.getByRole('tab', { name: /Đã hoàn thành/ }))
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(screen.getByRole('heading', { name: 'SQL' })).toBeVisible()
    await userEvent.click(screen.getByRole('tab', { name: /Đang học/ }))
    expect(screen.getAllByRole('article')).toHaveLength(2)
    expect(screen.queryByRole('heading', { name: 'Java' })).not.toBeInTheDocument()
  })
  it('supports keyboard tabs, pagination and sorting', async () => {
    render(<Harness courses={Array.from({ length: 8 }, (_, i) => ({ ...course, id: `c${i}`, title: `Khóa ${8 - i}` }))} />)
    expect(screen.getAllByRole('article')).toHaveLength(6)
    await userEvent.click(screen.getByRole('button', { name: 'Trang sau' }))
    expect(screen.getAllByRole('article')).toHaveLength(2)
    await userEvent.click(screen.getByRole('combobox', { name: 'Sắp xếp khóa học' }))
    await userEvent.click(screen.getByRole('option', { name: 'Tên A–Z' }))
    expect(screen.getAllByRole('article')[0]).toHaveTextContent('Khóa 1')
    screen.getByRole('tab', { name: /Tất cả/ }).focus()
    await userEvent.keyboard('{End}')
    expect(screen.getByRole('tab', { name: /Đã hoàn thành/ })).toHaveFocus()
    expect(screen.getByText('Chưa có khóa học hoàn thành')).toBeVisible()
  })
  it('opens a course from its title and joins from the empty library', async () => {
    const open = vi.fn(), join = vi.fn()
    const { rerender } = render(<Harness onOpen={open} onJoin={join} />)
    await userEvent.click(screen.getByRole('button', { name: 'Python' }))
    expect(open).toHaveBeenCalledWith(course)
    rerender(<Harness courses={[]} onJoin={join} />)
    await userEvent.click(screen.getAllByRole('button', { name: 'Tham gia lớp' })[1])
    expect(join).toHaveBeenCalledTimes(1)
  })
  it('retains visible courses if refreshing fails', async () => {
    const refresh = vi.fn().mockRejectedValue({ status: 0 })
    render(<Harness onRefresh={refresh} />)
    await userEvent.click(screen.getByRole('button', { name: 'Làm mới khóa học' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Không thể kết nối')
    expect(screen.getByRole('heading', { name: 'Python' })).toBeVisible()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Làm mới khóa học' })).toBeEnabled())
  })
  it('collapses additional classrooms without hiding access to their names', async () => {
    render(<Harness courses={[{ ...course, my_classrooms: Array.from({ length: 4 }, (_, i) => ({ id: `e${i}`, classroom_name: `Lớp ${i + 1}`, status: 'ACTIVE' })) }]} />)
    expect(screen.getByText('Lớp 3')).not.toBeVisible()
    await userEvent.click(screen.getByText('+2 lớp khác'))
    expect(screen.getByText('Lớp 3')).toBeVisible()
  })
})
