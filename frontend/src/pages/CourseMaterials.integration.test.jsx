import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TeacherHomePage from './TeacherHomePage'
import StudentHomePage from './StudentHomePage'
import { listAllCourses, listAllCourseMembers, getCourse } from '../services/course.service'

vi.mock('../services/course.service', async (importOriginal) => ({
  ...await importOriginal(), listAllCourses: vi.fn(), listAllCourseMembers: vi.fn(), getCourse: vi.fn(),
}))
vi.mock('../components/documents/CourseDocuments', () => ({
  default: ({ courseId, canManage = false }) => <section aria-label="Học liệu kiểm thử" data-course-id={courseId} data-manage={String(canManage)} />,
}))

const course = { id:'course-1', title:'Khóa tích hợp A+B', status:'PUBLISHED', description:'' }
describe('course material integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(window,'scrollTo').mockImplementation(() => {})
    listAllCourses.mockResolvedValue([course])
    listAllCourseMembers.mockResolvedValue([])
    getCourse.mockResolvedValue(course)
  })
  it('opens B materials within teacher course management', async () => {
    render(<TeacherHomePage user={{username:'teacher',role:'TEACHER'}} onLogout={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button',{name:/Quản lý/}))
    await userEvent.click(screen.getByRole('button',{name:'Học liệu'}))
    const materials = screen.getByRole('region',{name:'Học liệu kiểm thử'})
    expect(materials).toHaveAttribute('data-course-id','course-1')
    expect(materials).toHaveAttribute('data-manage','true')
  })
  it('shows B material metadata without teacher controls on the student detail', async () => {
    render(<StudentHomePage user={{username:'student',role:'STUDENT'}} onLogout={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button',{name:'Khóa học của tôi'}))
    await userEvent.click(screen.getByRole('button',{name:'Xem khóa học'}))
    const materials = await screen.findByRole('region',{name:'Học liệu kiểm thử'})
    expect(materials).toHaveAttribute('data-course-id','course-1')
    expect(materials).toHaveAttribute('data-manage','false')
  })
})
