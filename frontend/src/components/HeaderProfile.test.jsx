import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import HeaderProfile from './HeaderProfile'

const student = { username: 'anh', full_name: 'Nguyễn Minh Anh', role: 'STUDENT', email: 'anh@example.com', phone: '+84901234567', avatar_url: '/media/avatar.png', student_profile: { learning_goal: 'Học Python' } }
const teacher = { ...student, role: 'TEACHER', teacher_profile: { bio: 'Giáo viên lập trình', specialization: 'Django' } }

describe('header profile dropdown', () => {
  it.each([[student, 'Hồ sơ học viên', 'Học Python'], [teacher, 'Hồ sơ giáo viên', 'Django']])('opens role-specific profile on hover', async (user, label, content) => {
    render(<HeaderProfile user={user} onAccount={vi.fn()} />)
    const button = screen.getByRole('button', { name: 'Xem hồ sơ của bạn' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    await userEvent.hover(button)
    const panel = screen.getByRole('region', { name: label })
    expect(within(panel).getByText(content)).toBeVisible()
    expect(within(panel).getByText(user.email)).toBeVisible()
    expect(within(panel).getByText(user.phone)).toBeVisible()
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(within(button).getByRole('img')).toHaveAttribute('src', '/media/avatar.png')
    if (user.role === 'TEACHER') expect(within(panel).queryByText('Mục tiêu học tập')).not.toBeInTheDocument()
    else expect(within(panel).queryByText('Chuyên môn')).not.toBeInTheDocument()
  })

  it('keeps the dropdown open while moving into it and closes after leaving', async () => {
    render(<HeaderProfile user={student} onAccount={vi.fn()} />)
    await userEvent.hover(screen.getByRole('button', { name: 'Xem hồ sơ của bạn' }))
    const panel = screen.getByRole('region')
    await userEvent.hover(panel)
    expect(panel).toBeVisible()
    await userEvent.unhover(panel)
    await waitFor(() => expect(screen.queryByRole('region')).not.toBeInTheDocument())
  })

  it('opens by tap and closes with Escape or an outside click', () => {
    render(<HeaderProfile user={student} onAccount={vi.fn()} />)
    const button = screen.getByRole('button', { name: 'Xem hồ sơ của bạn' })
    fireEvent.click(button)
    expect(screen.getByRole('region')).toBeVisible()
    fireEvent.keyDown(button, { key: 'Escape' })
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
    expect(button).toHaveFocus()
    fireEvent.click(button)
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('region')).not.toBeInTheDocument()
  })

  it('supports keyboard navigation to account management', async () => {
    const onAccount = vi.fn()
    render(<HeaderProfile user={student} onAccount={onAccount} />)
    const button = screen.getByRole('button', { name: 'Xem hồ sơ của bạn' })
    button.focus()
    fireEvent.keyDown(button, { key: 'ArrowDown' })
    const manage = screen.getByRole('button', { name: 'Quản lý tài khoản' })
    await waitFor(() => expect(manage).toHaveFocus())
    await userEvent.keyboard('{Enter}')
    expect(onAccount).toHaveBeenCalledTimes(1)
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })

  it('renders initials and empty profile fallback safely', () => {
    render(<HeaderProfile user={{ username: 'student', role: 'STUDENT' }} onAccount={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Xem hồ sơ của bạn' }))
    expect(screen.getByText('Chưa cập nhật')).toBeVisible()
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})
