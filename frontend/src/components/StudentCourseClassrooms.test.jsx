import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import StudentCourseClassrooms from './StudentCourseClassrooms'
import { listMyCourseClassrooms } from '../services/course.service'

vi.mock('../services/course.service', async (original) => ({ ...await original(), listMyCourseClassrooms: vi.fn() }))
const classroom = { id: 'e1', classroom_id: 'room1', classroom_name: 'Lớp Python buổi tối', status: 'ACTIVE', progress_percent: 25, enrolled_at: '2026-10-08T10:00:00Z' }
const course = { id: 'c1', my_classrooms: [classroom] }
describe('student course classrooms', () => {
  beforeEach(() => vi.resetAllMocks())
  it('shows class names, status and progress from the course response', () => {
    render(<StudentCourseClassrooms course={course} onUpdated={vi.fn()} onUnavailable={vi.fn()} />)
    expect(screen.getByText('Lớp Python buổi tối')).toBeVisible()
    expect(screen.getByText('Đang học')).toBeVisible()
    expect(screen.getByRole('progressbar')).toHaveAttribute('value', '25')
  })
  it('refreshes own classrooms and synchronizes the course list', async () => {
    const updated = vi.fn()
    const classes = [{ ...classroom, status: 'COMPLETED', progress_percent: 100 }]
    listMyCourseClassrooms.mockResolvedValue(classes)
    render(<StudentCourseClassrooms course={course} onUpdated={updated} onUnavailable={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Làm mới lớp học của tôi' }))
    expect(await screen.findByText('Đã hoàn thành')).toBeVisible()
    expect(listMyCourseClassrooms).toHaveBeenCalledWith('c1')
    expect(updated).toHaveBeenCalledWith(classes)
  })
  it('notifies the page when access has been revoked', async () => {
    const unavailable = vi.fn()
    listMyCourseClassrooms.mockRejectedValue({ status: 403 })
    render(<StudentCourseClassrooms course={course} onUpdated={vi.fn()} onUnavailable={unavailable} />)
    await userEvent.click(screen.getByRole('button', { name: 'Làm mới lớp học của tôi' }))
    await waitFor(() => expect(unavailable).toHaveBeenCalledWith({ status: 403 }))
  })
  it('handles empty classrooms without inventing enrollment data', () => {
    render(<StudentCourseClassrooms course={{ id: 'c1', my_classrooms: [] }} onUpdated={vi.fn()} onUnavailable={vi.fn()} />)
    expect(screen.getByText('Chưa có thông tin lớp đang tham gia.')).toBeVisible()
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument()
  })
  it('paginates many classes and searches on the first result page', async () => {
    render(<StudentCourseClassrooms course={{ id: 'c1', my_classrooms: Array.from({ length: 8 }, (_, i) => ({ ...classroom, id: `e${i}`, classroom_name: `Nhóm ${i + 1}` })) }} />)
    expect(screen.getAllByRole('article')).toHaveLength(5)
    await userEvent.click(screen.getByRole('button', { name: 'Trang lớp sau' }))
    expect(screen.getAllByRole('article')).toHaveLength(3)
    await userEvent.type(screen.getByLabelText('Tìm lớp trong khóa học'), 'Nhóm 1')
    expect(screen.getAllByRole('article')).toHaveLength(1)
    expect(screen.getByText('Nhóm 1')).toBeVisible()
  })
})
