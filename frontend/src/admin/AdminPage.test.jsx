import { beforeEach, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AdminPage from './AdminPage'
import AccountsPage from './pages/AccountsPage'
import InstitutionsPage from './pages/InstitutionsPage'
import OperationsPage from './pages/OperationsPage'
import { NavigationProvider } from '../hooks/useHistoryState'
import { adminRequest, writeAdmin } from './services/admin.service'

vi.mock('./services/admin.service', async original => ({ ...await original(), adminRequest: vi.fn(), writeAdmin: vi.fn() }))
vi.mock('../components/HeaderProfile', () => ({ default: ({ onAccount }) => <button onClick={onAccount}>Hồ sơ của bạn</button> }))
const user = { id: 'admin-id', role: 'ADMIN', username: 'admin', full_name: 'Quản trị viên', status: 'ACTIVE' }
const target = { id: 'teacher-id', username: 'teacher', full_name: 'Giáo viên kiểm', role: 'TEACHER', status: 'ACTIVE', email: 'teacher@example.com', updated_at: '2026-11-27T01:00:00Z', teacher_profile: { approval: { status: 'PENDING', revision: 1 } } }
const caps = { accounts: true, teachers: true, institutions: true, operations: true, edit_account: true, decide_teacher: true, import_institutions: true }
beforeEach(() => { vi.resetAllMocks(); window.sessionStorage.clear(); window.history.replaceState(null, '', '/'); vi.spyOn(window, 'scrollTo').mockImplementation(() => {}) })

function mount(capabilities) {
  adminRequest.mockImplementation(async path => path === 'capabilities/' ? { user_id: user.id, capabilities } : { results: [], count: 0 })
  return render(<NavigationProvider owner={user.id}><AdminPage user={user} onLogout={vi.fn()} /></NavigationProvider>)
}
it('shows only permitted navigation and keeps the personal profile available', async () => {
  mount({ accounts: true })
  expect(await screen.findByRole('button', { name: 'Tài khoản', exact: true })).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Duyệt giáo viên', exact: true })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Hồ sơ cá nhân' })).toBeVisible()
})
it('renders custom filter comboboxes without native selects and supports keyboard selection', async () => {
  adminRequest.mockResolvedValue({ results: [], count: 0 })
  const { container } = render(<AccountsPage currentUser={user} capabilities={caps} />)
  const control = screen.getByRole('combobox', { name: 'Vai trò' })
  await userEvent.click(control)
  await userEvent.keyboard('{End}{Enter}')
  await waitFor(() => expect(adminRequest).toHaveBeenLastCalledWith(expect.stringContaining('role=ADMIN'), expect.anything()))
  expect(container.querySelector('select')).toBeNull()
})
it('does not show write actions for a read-only administrator', async () => {
  adminRequest.mockImplementation(async path => path.startsWith('users/teacher-id/') ? target : { results: [target], count: 1 })
  render(<AccountsPage currentUser={user} capabilities={{ accounts: true }} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Xem hồ sơ' }))
  expect(await screen.findByRole('dialog')).toBeVisible()
  expect(screen.queryByRole('button', { name: 'Đổi trạng thái' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Duyệt giảng dạy' })).not.toBeInTheDocument()
})
it('sends the displayed approval revision, reason and password only after confirmation', async () => {
  adminRequest.mockImplementation(async path => path.startsWith('users/teacher-id/') ? target : { results: [target], count: 1 })
  writeAdmin.mockResolvedValue({ status: 'APPROVED' })
  render(<AccountsPage currentUser={user} capabilities={caps} teachers />)
  await userEvent.click(await screen.findByRole('button', { name: 'Xem hồ sơ' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Duyệt giảng dạy' }))
  expect(writeAdmin).not.toHaveBeenCalled()
  await userEvent.type(screen.getByLabelText('Lý do thay đổi'), 'Đã đối chiếu')
  await userEvent.type(screen.getByLabelText('Mật khẩu Admin của bạn'), 'Private-Test-839!')
  await userEvent.click(screen.getByRole('button', { name: 'Xác nhận và lưu' }))
  expect(writeAdmin).toHaveBeenCalledWith('teachers/teacher-id/approval/', expect.objectContaining({ expected_revision: 1, status: 'APPROVED', reason: 'Đã đối chiếu' }), 'POST')
})
it('shows a conflict and requires reloading instead of retrying a stale write', async () => {
  adminRequest.mockImplementation(async path => path.startsWith('users/teacher-id/') ? target : { results: [target], count: 1 })
  writeAdmin.mockRejectedValue({ status: 409 })
  render(<AccountsPage currentUser={user} capabilities={caps} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Xem hồ sơ' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Đổi trạng thái' }))
  fireEvent.change(screen.getByLabelText('Lý do thay đổi'), { target: { value: 'Kiểm tra' } })
  fireEvent.change(screen.getByLabelText('Mật khẩu Admin của bạn'), { target: { value: 'Private-Test-839!' } })
  await userEvent.click(screen.getByRole('button', { name: 'Xác nhận và lưu' }))
  expect(await screen.findByRole('button', { name: 'Tải lại hồ sơ' })).toBeVisible()
  expect(screen.getByLabelText('Mật khẩu Admin của bạn')).toHaveValue('')
  expect(writeAdmin).toHaveBeenCalledTimes(1)
})
it('clears a prepared action when the administrator loses write permission', async () => {
  adminRequest.mockImplementation(async path => path.startsWith('users/teacher-id/') ? target : { results: [target], count: 1 })
  const view = render(<AccountsPage currentUser={user} capabilities={caps} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Xem hồ sơ' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Đổi trạng thái' }))
  expect(screen.getByLabelText('Mật khẩu Admin của bạn')).toBeVisible()
  view.rerender(<AccountsPage currentUser={user} capabilities={{ accounts: true }} />)
  expect(screen.queryByLabelText('Mật khẩu Admin của bạn')).not.toBeInTheDocument()
  expect(writeAdmin).not.toHaveBeenCalled()
})
it('discards old results when the account search changes', async () => {
  let finish
  adminRequest.mockImplementation(path => path.includes('q=new') ? Promise.resolve({ results: [], count: 0 }) : new Promise(resolve => { finish = resolve }))
  render(<AccountsPage currentUser={user} capabilities={caps} />)
  fireEvent.change(screen.getByLabelText('Tìm tài khoản'), { target: { value: 'new' } })
  await userEvent.click(screen.getByRole('button', { name: 'Tìm kiếm' }))
  await screen.findByText('Chưa có kết quả phù hợp.')
  finish({ results: [target], count: 1 })
  expect(screen.queryByText('Giáo viên kiểm')).not.toBeInTheDocument()
})
it('requires a new preview when the import file changes', async () => {
  adminRequest.mockImplementation(async path => path.includes('import') ? { valid: true, created: 1, updated: 0, unchanged: 0, errors: [] } : { results: [], has_more: false })
  render(<InstitutionsPage capabilities={caps} />)
  await userEvent.click(screen.getByRole('button', { name: 'Nhập CSV / XLSX' }))
  const input = screen.getByLabelText('File danh mục')
  await userEvent.upload(input, new File(['code,name'], 'schools.csv', { type: 'text/csv' }))
  await userEvent.click(screen.getByRole('button', { name: 'Kiểm tra và xem trước' }))
  expect(await screen.findByRole('button', { name: 'Xác nhận nhập' })).toBeEnabled()
  await userEvent.upload(input, new File(['changed'], 'other.csv', { type: 'text/csv' }))
  expect(screen.getByRole('button', { name: 'Xác nhận nhập' })).toBeDisabled()
})
it('keeps ingestion visible when AI telemetry is missing without claiming successful health', async () => {
  adminRequest.mockResolvedValue({ as_of: '2026-11-27T01:00:00Z', ai: null, ingestion: { states: [{ status: 'SUCCEEDED', count: 3 }], latest: null } })
  render(<OperationsPage />)
  expect(await screen.findByText('Chưa có dữ liệu kết quả.')).toBeVisible()
  expect(screen.getByText('Hoàn tất')).toBeVisible()
  expect(screen.queryByText('Sẵn sàng')).not.toBeInTheDocument()
  expect(screen.getByText('3')).toBeVisible()
})
it('reports missing account fields inline without native popups or sending a request', async () => {
  adminRequest.mockResolvedValue({ results: [], count: 0 })
  render(<AccountsPage currentUser={user} capabilities={{ ...caps, create_account: true }} />)
  await userEvent.click(screen.getByRole('button', { name: 'Tạo tài khoản', exact: true }))
  const dialog = screen.getByRole('dialog')
  await userEvent.click(within(dialog).getByRole('button', { name: 'Tạo tài khoản', exact: true }))
  expect(screen.getByText('Vui lòng nhập tên đăng nhập.')).toBeVisible()
  expect(screen.getByText('Vui lòng nhập mật khẩu ban đầu.')).toBeVisible()
  expect(screen.getByLabelText('Tên đăng nhập')).toHaveAttribute('aria-invalid', 'true')
  expect(screen.getByLabelText('Tên đăng nhập')).toHaveFocus()
  expect(dialog.querySelector('form')).toHaveAttribute('novalidate')
  expect(writeAdmin).not.toHaveBeenCalled()
  await userEvent.type(screen.getByLabelText('Tên đăng nhập'), 'teacher')
  expect(screen.queryByText('Vui lòng nhập tên đăng nhập.')).not.toBeInTheDocument()
  const initial = screen.getByLabelText('Mật khẩu ban đầu', { exact: true })
  expect(initial).toHaveAttribute('type', 'password')
  await userEvent.click(screen.getByRole('button', { name: 'Hiện mật khẩu ban đầu' }))
  expect(initial).toHaveAttribute('type', 'text')
  expect(screen.getByLabelText('Mật khẩu Admin của bạn', { exact: true })).toHaveAttribute('type', 'password')
  await userEvent.click(screen.getByRole('button', { name: 'Ẩn mật khẩu ban đầu' }))
  expect(initial).toHaveAttribute('type', 'password')
})
it('validates empty administrator confirmation fields before saving profile changes', async () => {
  adminRequest.mockImplementation(async path => path.startsWith('users/teacher-id/') ? target : { results: [target], count: 1 })
  render(<AccountsPage currentUser={user} capabilities={caps} />)
  await userEvent.click(await screen.findByRole('button', { name: 'Xem hồ sơ' }))
  await userEvent.click(await screen.findByRole('button', { name: 'Sửa thông tin' }))
  fireEvent.change(screen.getByLabelText('Họ và tên'), { target: { value: '' } })
  await userEvent.click(screen.getByRole('button', { name: 'Xác nhận và lưu' }))
  expect(screen.getByText('Vui lòng nhập họ và tên.')).toBeVisible()
  expect(screen.getByText('Vui lòng nhập lý do thay đổi.')).toBeVisible()
  expect(screen.getByText('Vui lòng nhập mật khẩu admin của bạn.')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: 'Hiện mật khẩu admin của bạn' }))
  expect(screen.getByLabelText('Mật khẩu Admin của bạn', { exact: true })).toHaveAttribute('type', 'text')
  expect(writeAdmin).not.toHaveBeenCalled()
})
it('validates manual institution creation inline, including HTTPS and required levels', async () => {
  adminRequest.mockResolvedValue({ results: [], has_more: false })
  render(<InstitutionsPage capabilities={{ institutions: true, create_institution: true }} />)
  await userEvent.click(screen.getByRole('button', { name: 'Thêm trường', exact: true }))
  const submit = screen.getByRole('button', { name: 'Lưu thông tin trường' })
  await userEvent.click(submit)
  for (const message of ['Vui lòng nhập mã nội bộ.', 'Vui lòng nhập tên trường.', 'Vui lòng nhập tỉnh / thành phố.', 'Vui lòng nhập đường dẫn nguồn https.', 'Vui lòng nhập ngày đối chiếu nguồn.']) {
    expect(screen.getByText(message)).toBeVisible()
  }
  expect(screen.getByLabelText('Mã nội bộ')).toHaveFocus()
  expect(writeAdmin).not.toHaveBeenCalled()
  for (const [label, value] of [['Mã nội bộ', 'school-test'], ['Tên trường', 'Trường kiểm thử'], ['Tỉnh / thành phố', 'Hà Nội'], ['Đường dẫn nguồn HTTPS', 'http://example.edu.vn'], ['Ngày đối chiếu nguồn', '2026-11-27']]) {
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
  }
  await userEvent.click(screen.getByRole('checkbox', { name: 'Đại học', exact: true }))
  await userEvent.click(submit)
  expect(screen.getByText('Vui lòng chọn ít nhất một cấp học.')).toBeVisible()
  expect(screen.getByText('Vui lòng nhập đường dẫn nguồn bắt đầu bằng https://.')).toBeVisible()
  expect(writeAdmin).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText('Đường dẫn nguồn HTTPS'), { target: { value: 'https://example.edu.vn' } })
  await userEvent.click(screen.getByRole('checkbox', { name: 'Đại học', exact: true }))
  writeAdmin.mockResolvedValue({})
  await userEvent.click(submit)
  expect(writeAdmin).toHaveBeenCalledWith('institutions/', expect.objectContaining({ code: 'school-test', levels: ['UNIVERSITY'], campus: '', external_code: '' }), 'POST')
})
