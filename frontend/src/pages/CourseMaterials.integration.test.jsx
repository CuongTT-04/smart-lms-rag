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
  it('keeps course materials out of teacher course management', async () => {
    render(<TeacherHomePage user={{username:'teacher',role:'TEACHER'}} onLogout={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button',{name:/Quản lý/}))
    expect(screen.queryByRole('button',{name:'Học liệu'})).not.toBeInTheDocument()
    expect(screen.queryByRole('region',{name:'Học liệu kiểm thử'})).not.toBeInTheDocument()
  })
  it('keeps course materials out of the student detail', async () => {
    render(<StudentHomePage user={{username:'student',role:'STUDENT'}} onLogout={vi.fn()} />)
    await userEvent.click(await screen.findByRole('button',{name:'Khóa học của tôi'}))
    await userEvent.click(screen.getByRole('button',{name:'Xem khóa học'}))
    await screen.findByRole('heading', {name: course.title})
    expect(screen.queryByRole('region',{name:'Học liệu kiểm thử'})).not.toBeInTheDocument()
  })
})
