import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LoginPage from './LoginPage'
import { login } from '../services/auth.service'

vi.mock('../services/auth.service', async (importOriginal) => ({ ...await importOriginal(), login: vi.fn() }))

describe('Vietnamese login form', () => {
  beforeEach(() => vi.mocked(login).mockReset())

  it('links to registration and password recovery instead of support', () => {
    render(<LoginPage onAuthenticated={vi.fn()} />)
    expect(screen.getByText('Chưa có tài khoản?')).toBeVisible()
    expect(screen.getByRole('link', { name: 'Đăng ký', exact: true })).toHaveAttribute('href', '/register')
    expect(screen.getByRole('link', { name: 'Quên mật khẩu?' })).toHaveAttribute('href', '/forgot-password')
    expect(screen.queryByText('Liên hệ hỗ trợ')).not.toBeInTheDocument()
  })

  it('validates empty fields and focuses username without calling API', async () => {
    render(<LoginPage onAuthenticated={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: 'Đăng nhập', exact: true }))
    expect(screen.getByText('Vui lòng nhập tên đăng nhập.')).toBeVisible()
    expect(screen.getByText('Vui lòng nhập mật khẩu.')).toBeVisible()
    expect(screen.getByLabelText('Tên đăng nhập')).toHaveFocus()
    expect(login).not.toHaveBeenCalled()
  })

  it('toggles password visibility', async () => {
    render(<LoginPage onAuthenticated={vi.fn()} />)
    expect(screen.getByLabelText('Mật khẩu', { exact: true })).toHaveAttribute('type', 'password')
    await userEvent.click(screen.getByRole('button', { name: 'Hiện mật khẩu' }))
    expect(screen.getByLabelText('Mật khẩu', { exact: true })).toHaveAttribute('type', 'text')
    await userEvent.click(screen.getByRole('button', { name: 'Ẩn mật khẩu' }))
    expect(screen.getByLabelText('Mật khẩu', { exact: true })).toHaveAttribute('type', 'password')
  })

  it('submits once while pending and completes login', async () => {
    let resolve
    login.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const onAuthenticated = vi.fn()
    render(<LoginPage onAuthenticated={onAuthenticated} />)
    await userEvent.type(screen.getByLabelText('Tên đăng nhập'), 'student')
    await userEvent.type(screen.getByLabelText('Mật khẩu', { exact: true }), ' secret ')
    const form = screen.getByRole('button', { name: 'Đăng nhập', exact: true }).closest('form')
    fireEvent.submit(form)
    fireEvent.submit(form)
    expect(login).toHaveBeenCalledTimes(1)
    expect(login).toHaveBeenCalledWith('student', ' secret ')
    expect(screen.getByRole('button', { name: 'Đang đăng nhập' })).toBeDisabled()
    resolve({ username: 'student' })
    await waitFor(() => expect(onAuthenticated).toHaveBeenCalledWith({ username: 'student' }))
    expect(screen.getByLabelText('Mật khẩu', { exact: true })).toHaveValue('')
  })

  it.each([401, 403, 0])('shows a safe Vietnamese error for %s and permits retry', async (status) => {
    login.mockRejectedValueOnce({ status })
    render(<LoginPage onAuthenticated={vi.fn()} />)
    await userEvent.type(screen.getByLabelText('Tên đăng nhập'), 'student')
    await userEvent.type(screen.getByLabelText('Mật khẩu', { exact: true }), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Đăng nhập', exact: true }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/Vui lòng|Tên đăng nhập|quyền/)
    expect(screen.getByRole('button', { name: 'Đăng nhập', exact: true })).toBeEnabled()
  })
})
