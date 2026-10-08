import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RegisterPage from './RegisterPage'
import ForgotPasswordPage from './ForgotPasswordPage'
import ResetPasswordPage from './ResetPasswordPage'
import { registerAccount, requestPasswordReset, confirmPasswordReset } from '../services/auth.service'

vi.mock('../services/auth.service', async (original) => ({
  ...await original(), registerAccount: vi.fn(), requestPasswordReset: vi.fn(), confirmPasswordReset: vi.fn(),
}))

async function fillRegistration(role = 'Học viên') {
  await userEvent.click(screen.getByRole('radio', { name: role }))
  fireEvent.change(screen.getByLabelText('Họ và tên'), { target: { value: 'Nguyễn Minh Anh' } })
  fireEvent.change(screen.getByLabelText('Tên đăng nhập'), { target: { value: 'minhanh' } })
  fireEvent.change(screen.getByLabelText('Email', { exact: true }), { target: { value: 'anh@example.com' } })
  fireEvent.change(screen.getByLabelText('Mật khẩu', { exact: true }), { target: { value: 'Ohayo-Secure-839!' } })
  fireEvent.change(screen.getByLabelText('Xác nhận mật khẩu', { exact: true }), { target: { value: 'Ohayo-Secure-839!' } })
}

function fillReset(password = 'New-Ohayo-Secure-839!') {
  fireEvent.change(screen.getByLabelText('Mật khẩu mới', { exact: true }), { target: { value: password } })
  fireEvent.change(screen.getByLabelText('Xác nhận mật khẩu', { exact: true }), { target: { value: password } })
}

describe('registration and password recovery', () => {
  beforeEach(() => {
    vi.mocked(registerAccount).mockReset()
    vi.mocked(requestPasswordReset).mockReset()
    vi.mocked(confirmPasswordReset).mockReset()
    window.history.replaceState(null, '', '/')
  })

  it('requires explicit role selection and minimum signup fields', async () => {
    render(<RegisterPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Đăng ký', exact: true }))
    expect(screen.getByText('Vui lòng chọn Học viên hoặc Giáo viên.')).toBeVisible()
    expect(screen.getByRole('radio', { name: 'Học viên' })).toHaveFocus()
    expect(registerAccount).not.toHaveBeenCalled()
  })

  it.each([['Học viên', 'STUDENT'], ['Giáo viên', 'TEACHER']])('registers a %s without extra profile data or automatic login', async (label, role) => {
    registerAccount.mockResolvedValueOnce({ role })
    render(<RegisterPage />)
    await fillRegistration(label)
    await userEvent.click(screen.getByRole('button', { name: 'Đăng ký', exact: true }))
    expect(await screen.findByRole('heading', { name: 'Đăng ký thành công' })).toBeVisible()
    expect(registerAccount).toHaveBeenCalledWith({
      full_name: 'Nguyễn Minh Anh', username: 'minhanh', email: 'anh@example.com',
      role, password: 'Ohayo-Secure-839!', password_confirm: 'Ohayo-Secure-839!',
    })
    expect(screen.getByRole('link', { name: 'Đăng nhập ngay' })).toHaveAttribute('href', '/')
  })

  it('maps backend duplicate fields and allows retry', async () => {
    registerAccount.mockRejectedValueOnce({ status: 400, data: { email: ['Already registered.'] } })
    render(<RegisterPage />)
    await fillRegistration()
    await userEvent.click(screen.getByRole('button', { name: 'Đăng ký', exact: true }))
    expect(await screen.findByText('Email không hợp lệ hoặc đã được sử dụng.')).toBeVisible()
    expect(screen.getByLabelText('Email', { exact: true })).toHaveFocus()
    expect(screen.getByRole('button', { name: 'Đăng ký', exact: true })).toBeEnabled()
  })

  it('blocks double submission while registration is pending', async () => {
    let resolve
    registerAccount.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    render(<RegisterPage />)
    await fillRegistration()
    const form = screen.getByRole('button', { name: 'Đăng ký', exact: true }).closest('form')
    fireEvent.submit(form)
    fireEvent.submit(form)
    expect(registerAccount).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Đang tạo tài khoản' })).toBeDisabled()
    resolve({ role: 'STUDENT' })
    await screen.findByText('Đăng ký thành công')
  })

  it('rejects password mismatch before calling registration API', async () => {
    render(<RegisterPage />)
    await fillRegistration()
    fireEvent.change(screen.getByLabelText('Xác nhận mật khẩu', { exact: true }), { target: { value: 'different' } })
    await userEvent.click(screen.getByRole('button', { name: 'Đăng ký', exact: true }))
    expect(screen.getByText('Mật khẩu xác nhận không khớp.')).toBeVisible()
    expect(registerAccount).not.toHaveBeenCalled()
  })

  it.each(['abcdefgh1!', 'Abcdefgh!', 'Abcdefg1', 'Abcdef1 '])('blocks invalid registration password %j before API', async (password) => {
    render(<RegisterPage />)
    await fillRegistration()
    fireEvent.change(screen.getByLabelText('Mật khẩu', { exact: true }), { target: { value: password } })
    fireEvent.change(screen.getByLabelText('Xác nhận mật khẩu', { exact: true }), { target: { value: password } })
    await userEvent.click(screen.getByRole('button', { name: 'Đăng ký', exact: true }))
    expect(screen.getByLabelText('Mật khẩu', { exact: true })).toHaveAttribute('aria-invalid', 'true')
    expect(registerAccount).not.toHaveBeenCalled()
  })

  it.each(['abcdefgh1!', 'Abcdefgh!', 'Abcdefg1', 'Abcdef1 '])('blocks invalid reset password %j before API', async (password) => {
    window.history.replaceState(null, '', '/reset-password?uid=user-uid&token=valid')
    render(<ResetPasswordPage />)
    fillReset(password)
    await userEvent.click(screen.getByRole('button', { name: 'Lưu mật khẩu mới' }))
    expect(screen.getByLabelText('Mật khẩu mới', { exact: true })).toHaveAttribute('aria-invalid', 'true')
    expect(confirmPasswordReset).not.toHaveBeenCalled()
  })

  it('validates recovery email locally', async () => {
    render(<ForgotPasswordPage />)
    await userEvent.click(screen.getByRole('button', { name: 'Gửi liên kết đặt lại' }))
    expect(screen.getByText('Vui lòng nhập email hợp lệ.')).toBeVisible()
    expect(requestPasswordReset).not.toHaveBeenCalled()
  })

  it('shows the generic email confirmation without exposing account existence', async () => {
    requestPasswordReset.mockResolvedValueOnce({ detail: 'generic' })
    render(<ForgotPasswordPage />)
    fireEvent.change(screen.getByLabelText('Email tài khoản'), { target: { value: 'unknown@example.com' } })
    await userEvent.click(screen.getByRole('button', { name: 'Gửi liên kết đặt lại' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Nếu email unknown@example.com thuộc tài khoản hợp lệ')
    await userEvent.click(screen.getByRole('button', { name: 'Nhập email khác' }))
    expect(screen.getByLabelText('Email tài khoản')).toBeVisible()
  })

  it('navigates directly to the development reset link on the current origin', async () => {
    requestPasswordReset.mockResolvedValueOnce({ reset_url: 'http://localhost:5173/reset-password?uid=test-uid&token=test-token' })
    const onNavigate = vi.fn()
    render(<ForgotPasswordPage onNavigate={onNavigate} />)
    fireEvent.change(screen.getByLabelText('Email tài khoản'), { target: { value: 'anh@example.com' } })
    await userEvent.click(screen.getByRole('button', { name: 'Gửi liên kết đặt lại' }))
    expect(onNavigate).toHaveBeenCalledWith('/reset-password?uid=test-uid&token=test-token')
    expect(screen.queryByText('Yêu cầu đã được tiếp nhận')).not.toBeInTheDocument()
  })

  it.each([429, 0])('shows recoverable errors for reset request HTTP %s', async (status) => {
    requestPasswordReset.mockRejectedValueOnce({ status })
    render(<ForgotPasswordPage />)
    fireEvent.change(screen.getByLabelText('Email tài khoản'), { target: { value: 'anh@example.com' } })
    await userEvent.click(screen.getByRole('button', { name: 'Gửi liên kết đặt lại' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Vui lòng')
    expect(screen.getByRole('button', { name: 'Gửi liên kết đặt lại' })).toBeEnabled()
  })

  it('rejects missing reset link parameters without a request', () => {
    render(<ResetPasswordPage />)
    expect(screen.getByRole('alert')).toHaveTextContent('Liên kết không hợp lệ')
    expect(screen.getByRole('link', { name: 'Gửi liên kết mới' })).toHaveAttribute('href', '/forgot-password')
    expect(confirmPasswordReset).not.toHaveBeenCalled()
  })

  it('submits email link parameters, preserves password spaces and removes secrets on success', async () => {
    window.history.replaceState(null, '', '/reset-password?uid=user-uid&token=reset-token')
    confirmPasswordReset.mockResolvedValueOnce({ detail: 'success' })
    render(<ResetPasswordPage />)
    fillReset('  New-Ohayo-Secure-839!  ')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu mật khẩu mới' }))
    expect(await screen.findByText('Đổi mật khẩu thành công')).toBeVisible()
    expect(confirmPasswordReset).toHaveBeenCalledWith({ uid: 'user-uid', token: 'reset-token', password: '  New-Ohayo-Secure-839!  ', password_confirm: '  New-Ohayo-Secure-839!  ' })
    expect(window.location.search).toBe('')
  })

  it('offers a new link when the server rejects an expired token', async () => {
    window.history.replaceState(null, '', '/reset-password?uid=user-uid&token=expired')
    confirmPasswordReset.mockRejectedValueOnce({ status: 400, data: { token: ['Expired'] } })
    render(<ResetPasswordPage />)
    fillReset()
    await userEvent.click(screen.getByRole('button', { name: 'Lưu mật khẩu mới' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('đã hết hạn')
    expect(screen.queryByLabelText('Mật khẩu mới', { exact: true })).not.toBeInTheDocument()
  })

  it('keeps the reset form available when password validators reject a password', async () => {
    window.history.replaceState(null, '', '/reset-password?uid=user-uid&token=valid')
    confirmPasswordReset.mockRejectedValueOnce({ status: 400, data: { password: ['Too common'] } })
    render(<ResetPasswordPage />)
    fillReset('Password1!')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu mật khẩu mới' }))
    await waitFor(() => expect(screen.getByLabelText('Mật khẩu mới', { exact: true })).toHaveFocus())
    expect(screen.getByLabelText('Mật khẩu mới', { exact: true })).toHaveAttribute('aria-invalid', 'true')
  })
})
