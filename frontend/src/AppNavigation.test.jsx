import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { currentUser } from './services/auth.service'

vi.mock('./services/auth.service', async (original) => ({ ...await original(), currentUser: vi.fn(), logout: vi.fn(async () => undefined) }))
vi.mock('./services/course.service', async (original) => ({ ...await original(),
  listAllCourses: vi.fn(async () => [{ id: 'python', title: 'Python', description: '', status: 'PUBLISHED' }]),
  listAllCourseMembers: vi.fn(async () => []),
  getCourse: vi.fn(async () => ({ id: 'python', title: 'Python', description: '', status: 'PUBLISHED' })),
  listMyCourseClassrooms: vi.fn(async () => []),
}))

beforeEach(() => vi.spyOn(window, 'scrollTo').mockImplementation(() => {}))

it.each(['TEACHER', 'STUDENT'])('restores the %s course after session bootstrap on reload, and clears it on logout', async (role) => {
  const owner = `reload-${role}`
  currentUser.mockResolvedValue({ id: owner, role, username: 'cuong', full_name: 'Cường', status: 'ACTIVE' })
  const first = render(<App />)
  await screen.findByText('Python')
  await userEvent.click(screen.getByRole('button', { name: role === 'TEACHER' ? 'Khóa học' : 'Khóa học của tôi', exact: true }))
  await userEvent.click(screen.getByRole('button', { name: role === 'TEACHER' ? /Quản lý khóa học Python/ : 'Xem khóa học', exact: role !== 'TEACHER' }))
  if (role === 'TEACHER') await screen.findByLabelText('Tên khóa học')
  else await screen.findByRole('heading', { name: 'Python', level: 1 })
  first.unmount()
  window.history.replaceState(null, '', '/')
  render(<App />)
  if (role === 'TEACHER') expect(await screen.findByLabelText('Tên khóa học')).toHaveValue('Python')
  else expect(await screen.findByRole('heading', { name: 'Python', level: 1 })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Đăng xuất', exact: true }))
  expect(await screen.findByLabelText('Tên đăng nhập')).toBeVisible()
  expect(window.sessionStorage.getItem(`ohayo.navigation.${owner}`)).toBeNull()
})
