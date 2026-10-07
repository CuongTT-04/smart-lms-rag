import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ProfileEditor from './ProfileEditor'
import { updateProfile, uploadAvatar } from '../services/profile.service'

vi.mock('../services/profile.service', async (original) => ({ ...await original(), updateProfile: vi.fn(), uploadAvatar: vi.fn() }))

const student = { id: 'student-id', role: 'STUDENT', status: 'ACTIVE', username: 'minhanh', full_name: 'Nguyễn Minh Anh', email: 'anh@example.com', phone: '', avatar_url: '', student_profile: { learning_goal: 'Học Python' } }
const teacher = { ...student, role: 'TEACHER', student_profile: undefined, teacher_profile: { bio: 'Giáo viên', specialization: 'Python' } }
const change = (label, value) => fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } })

describe('profile management', () => {
  beforeEach(() => {
    vi.mocked(updateProfile).mockReset()
    vi.mocked(uploadAvatar).mockReset()
    URL.createObjectURL = vi.fn(() => 'blob:preview')
    URL.revokeObjectURL = vi.fn()
  })

  it('saves only changed account fields and updates the parent', async () => {
    const updated = { ...student, full_name: 'Tên mới' }
    updateProfile.mockResolvedValueOnce({ user: updated, requires_login: false })
    const onUserUpdated = vi.fn()
    render(<ProfileEditor user={student} onUserUpdated={onUserUpdated} />)
    change('Họ và tên', 'Tên mới')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }))
    expect(updateProfile).toHaveBeenCalledWith({ full_name: 'Tên mới' })
    expect(onUserUpdated).toHaveBeenCalledWith(updated)
    expect(await screen.findByText('Đã lưu thay đổi.')).toBeVisible()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it.each([[student, 'Mục tiêu học tập', 'student_profile', 'learning_goal'], [teacher, 'Giới thiệu', 'teacher_profile', 'bio']])('edits the matching role profile', async (user, label, profile, field) => {
    updateProfile.mockResolvedValueOnce({ user: { ...user, [profile]: { ...user[profile], [field]: 'Nội dung mới' } } })
    render(<ProfileEditor user={user} />)
    await userEvent.click(screen.getByRole('tab', { name: 'Hồ sơ' }))
    change(label, 'Nội dung mới')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }))
    expect(updateProfile).toHaveBeenCalledWith({ [profile]: { [field]: 'Nội dung mới' } })
    expect(await screen.findByText('Đã lưu thay đổi.')).toBeVisible()
  })

  it('requires the current password when changing email', async () => {
    render(<ProfileEditor user={student} />)
    change('Email', 'new@example.com')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }))
    expect(screen.getByText('Vui lòng nhập mật khẩu hiện tại để đổi email.')).toBeVisible()
    expect(updateProfile).not.toHaveBeenCalled()
    updateProfile.mockResolvedValueOnce({ user: { ...student, email: 'new@example.com' } })
    change('Mật khẩu hiện tại', 'Old-Ohayo-839!')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }))
    expect(updateProfile).toHaveBeenCalledWith({ email: 'new@example.com', current_password: 'Old-Ohayo-839!' })
  })

  it('validates password complexity and requests sign-in after a successful change', async () => {
    const onSessionExpired = vi.fn()
    render(<ProfileEditor user={student} onSessionExpired={onSessionExpired} />)
    await userEvent.click(screen.getByRole('tab', { name: 'Bảo mật' }))
    change('Mật khẩu hiện tại', 'Old-Ohayo-839!')
    change('Mật khẩu mới', 'weak')
    change('Xác nhận mật khẩu', 'weak')
    await userEvent.click(screen.getByRole('button', { name: 'Đổi mật khẩu' }))
    expect(updateProfile).not.toHaveBeenCalled()
    change('Mật khẩu mới', 'New-Ohayo-849!')
    change('Xác nhận mật khẩu', 'New-Ohayo-849!')
    updateProfile.mockResolvedValueOnce({ user: student, requires_login: true })
    await userEvent.click(screen.getByRole('button', { name: 'Đổi mật khẩu' }))
    expect(onSessionExpired).toHaveBeenCalledWith('Đổi mật khẩu thành công. Vui lòng đăng nhập lại.')
  })

  it('shows nested backend errors and allows retry', async () => {
    updateProfile.mockRejectedValueOnce({ status: 400, data: { student_profile: { learning_goal: ['Too long'] } } })
    render(<ProfileEditor user={student} />)
    await userEvent.click(screen.getByRole('tab', { name: 'Hồ sơ' }))
    change('Mục tiêu học tập', 'New')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu thay đổi' }))
    expect(await screen.findByText('Mục tiêu học tập không được vượt quá 5000 ký tự.')).toBeVisible()
    expect(screen.getByRole('button', { name: 'Lưu thay đổi' })).toBeEnabled()
  })

  it('previews and uploads a local image, then releases the preview URL', async () => {
    const onUserUpdated = vi.fn()
    uploadAvatar.mockResolvedValueOnce({ ...student, avatar_url: '/media/avatar.jpg' })
    render(<ProfileEditor user={student} onUserUpdated={onUserUpdated} />)
    const file = new File(['image bytes'], 'avatar.jpg', { type: 'image/jpeg' })
    await userEvent.upload(screen.getByLabelText('Chọn ảnh đại diện từ máy'), file)
    expect(screen.getByRole('img')).toHaveAttribute('src', 'blob:preview')
    await userEvent.click(screen.getByRole('button', { name: 'Lưu ảnh' }))
    expect(uploadAvatar).toHaveBeenCalledWith(file)
    expect(onUserUpdated).toHaveBeenCalledWith({ ...student, avatar_url: '/media/avatar.jpg' })
    expect(await screen.findByText('Đã cập nhật ảnh đại diện.')).toBeVisible()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:preview')
  })

  it('rejects oversized local images without uploading', () => {
    render(<ProfileEditor user={student} />)
    const file = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'big.png', { type: 'image/png' })
    fireEvent.change(screen.getByLabelText('Chọn ảnh đại diện từ máy'), { target: { files: [file] } })
    expect(screen.getByText('Vui lòng chọn ảnh JPG, PNG hoặc WebP không quá 5 MB.')).toBeVisible()
    expect(uploadAvatar).not.toHaveBeenCalled()
  })

  it('removes an avatar through PATCH and notifies the parent', async () => {
    updateProfile.mockResolvedValueOnce({ user: student })
    render(<ProfileEditor user={{ ...student, avatar_url: '/media/old.jpg' }} />)
    await userEvent.click(screen.getByRole('button', { name: 'Xóa ảnh đại diện' }))
    expect(updateProfile).toHaveBeenCalledWith({ avatar_url: '' })
    expect(await screen.findByText('Đã xóa ảnh đại diện.')).toBeVisible()
  })

  it('blocks duplicate saves and expires an invalid session', async () => {
    let reject
    updateProfile.mockImplementationOnce(() => new Promise((resolve, fail) => { reject = fail }))
    const onSessionExpired = vi.fn()
    render(<ProfileEditor user={student} onSessionExpired={onSessionExpired} />)
    change('Họ và tên', 'New')
    const button = screen.getByRole('button', { name: 'Lưu thay đổi' })
    fireEvent.click(button)
    fireEvent.click(button)
    expect(updateProfile).toHaveBeenCalledTimes(1)
    expect(button).toBeDisabled()
    reject({ status: 401 })
    await waitFor(() => expect(onSessionExpired).toHaveBeenCalled())
  })
})
