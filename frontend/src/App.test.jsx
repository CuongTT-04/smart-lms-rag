import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { currentUser, logout } from './services/auth.service'
import { updateProfile } from './services/profile.service'

vi.mock('./services/auth.service', async (importOriginal) => ({ ...await importOriginal(), currentUser: vi.fn(), logout: vi.fn() }))
vi.mock('./services/profile.service', async (original) => ({ ...await original(), updateProfile: vi.fn() }))
const user = { username: 'admin', full_name: 'Nguyễn Minh Anh', email: '', role: 'ADMIN', status: 'ACTIVE' }

describe('authentication lifecycle', () => {
  beforeEach(() => { currentUser.mockReset(); logout.mockReset(); updateProfile.mockReset(); window.history.replaceState(null, '', '/') })

  it.each([
    ['/register', 'Tạo tài khoản OHAYO'], ['/forgot-password', 'Quên mật khẩu?'],
    ['/reset-password?uid=test&token=test', 'Đặt mật khẩu mới'],
  ])('opens public route %s directly without session lookup', (path, heading) => {
    window.history.replaceState(null, '', path)
    render(<App />)
    expect(screen.getByRole('heading', { name: heading })).toBeVisible()
    expect(currentUser).not.toHaveBeenCalled()
  })

  it('shows the login screen for an anonymous session without an error', async () => {
    currentUser.mockResolvedValueOnce(null)
    render(<App />)
    expect(await screen.findByLabelText('Tên đăng nhập')).toBeVisible()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('restores authenticated user and logs out', async () => {
    currentUser.mockResolvedValueOnce(user)
    logout.mockResolvedValueOnce(undefined)
    render(<App />)
    expect(await screen.findByRole('heading', { name: 'Xin chào, Nguyễn Minh Anh!' })).toBeVisible()
    expect(screen.getByText('Quản trị viên')).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: 'Đăng xuất' }))
    expect(await screen.findByLabelText('Tên đăng nhập')).toBeVisible()
    expect(logout).toHaveBeenCalledTimes(1)
  })

  it('does not silently clear a valid session on authorization failure', async () => {
    currentUser.mockResolvedValue(user)
    logout.mockRejectedValueOnce({ status: 403 })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Đăng xuất' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('quyền')
    expect(screen.getByRole('heading', { name: 'Xin chào, Nguyễn Minh Anh!' })).toBeVisible()
  })

  it('returns to login when the session really expired', async () => {
    currentUser.mockResolvedValueOnce(user).mockRejectedValueOnce({ status: 401 })
    logout.mockRejectedValueOnce({ status: 401 })
    render(<App />)
    await userEvent.click(await screen.findByRole('button', { name: 'Đăng xuất' }))
    await waitFor(() => expect(screen.getByLabelText('Tên đăng nhập')).toBeVisible())
  })

  it('shows a connection error when session lookup is unavailable', async () => {
    currentUser.mockRejectedValueOnce({ status: 0 })
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('Không thể kết nối')
  })

  it('updates the authenticated account after saving profile changes', async () => {
    currentUser.mockResolvedValueOnce({ ...user, id: 'admin-id' })
    updateProfile.mockResolvedValueOnce({ user: { ...user, id: 'admin-id', full_name: 'Tên mới' }, requires_login: false })
    render(<App />)
    fireEvent.change(await screen.findByLabelText('Họ và tên'), { target: { value: 'Tên mới' } })
    await userEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }))
    expect(await screen.findByRole('heading', { name: 'Xin chào, Tên mới!' })).toBeVisible()
  })

  it('returns to login with a success notice after changing password', async () => {
    currentUser.mockResolvedValueOnce(user)
    updateProfile.mockResolvedValueOnce({ user, requires_login: true })
    render(<App />)
    await userEvent.click(await screen.findByRole('tab', { name: 'Bảo mật' }))
    for (const [label, value] of [['Mật khẩu hiện tại', 'Old-Ohayo-839!'], ['Mật khẩu mới', 'New-Ohayo-849!'], ['Xác nhận mật khẩu', 'New-Ohayo-849!']]) {
      fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } })
    }
    await userEvent.click(screen.getByRole('button', { name: 'Đổi mật khẩu' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Đổi mật khẩu thành công. Vui lòng đăng nhập lại.')
    expect(screen.getByRole('button', { name: 'Đăng nhập', exact: true })).toBeVisible()
  })

})
