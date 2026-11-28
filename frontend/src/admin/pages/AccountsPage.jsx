import { useRef, useState } from 'react'
import { Plus, Search, ShieldCheck } from 'lucide-react'
import InstitutionCombobox from '../../components/InstitutionCombobox'
import useAdminData from '../hooks/useAdminData'
import { adminError, writeAdmin } from '../services/admin.service'
import { Feedback, Field, Modal, Pagination, SelectField, Status, ValidatedForm } from '../components/AdminControls'
import { APPROVALS, auditAction, approvalSource, dateText, labelOf, ROLES, STATUSES } from '../components/admin-format'

const ALL = [['', 'Tất cả']]

export default function AccountsPage({ teachers = false, capabilities, initialFilters = {}, currentUser }) {
  const [filters, setFilters] = useState({ q: '', role: '', status: '', approval_status: '', ...initialFilters })
  const [search, setSearch] = useState(filters.q)
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState(null)
  const [creating, setCreating] = useState(false)
  const [notice, setNotice] = useState('')
  const params = new URLSearchParams({ ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value)), offset, limit: 20 })
  const resource = useAdminData(`${teachers ? 'teachers' : 'users'}/?${params}`)
  const update = (key, value) => { setFilters(old => ({ ...old, [key]: value })); setOffset(0) }
  const saved = () => { setNotice('Đã lưu thay đổi.'); resource.refresh() }
  return <><div className="adm-page-heading"><div><p className="adm-eyebrow">QUẢN LÝ CON NGƯỜI</p><h1>{teachers ? 'Duyệt giáo viên' : 'Tài khoản'}</h1><p>{teachers ? 'Đối chiếu hồ sơ và quyết định quyền giảng dạy.' : 'Tra cứu hồ sơ, quản lý trạng thái và vai trò.'}</p></div>{!teachers && capabilities.create_account && <button className="solid-button" onClick={() => setCreating(true)}><Plus size={17} /> Tạo tài khoản</button>}</div>
    <form className="adm-toolbar" onSubmit={e => { e.preventDefault(); update('q', search.trim()) }}><div className="adm-search"><Search size={18} /><input aria-label="Tìm tài khoản" placeholder="Tên, email hoặc tên đăng nhập" value={search} onChange={e => setSearch(e.target.value)} /></div>{!teachers && <SelectField label="Vai trò" value={filters.role} onChange={v => update('role', v)} options={[...ALL, ...ROLES]} />}{teachers ? <SelectField label="Trạng thái duyệt" value={filters.approval_status} onChange={v => update('approval_status', v)} options={[...ALL, ...APPROVALS]} /> : <SelectField label="Trạng thái tài khoản" value={filters.status} onChange={v => update('status', v)} options={[...ALL, ...STATUSES]} />}<button className="secondary-button">Tìm kiếm</button></form>
    {notice && <p className="adm-info" role="status">{notice}</p>}<div className="adm-panel adm-table-panel"><Feedback resource={resource} empty={resource.data?.results.length === 0}><div className="adm-table-scroll"><table><thead><tr><th>Tài khoản</th><th>{teachers ? 'Trường công tác' : 'Vai trò'}</th><th>Trạng thái</th><th>Email</th><th><span className="sr-only">Thao tác</span></th></tr></thead><tbody>{resource.data?.results.map(row => <tr key={row.id}><td><strong>{row.full_name || row.username}</strong><small>@{row.username}</small></td><td>{teachers ? row.teacher_profile?.institution?.name || row.teacher_profile?.institution_other_name || 'Chưa khai báo' : labelOf(ROLES, row.role)}</td><td><Status tone={(teachers ? row.teacher_profile?.approval?.status : row.status) === 'APPROVED' || (!teachers && row.status === 'ACTIVE') ? 'good' : 'muted'}>{labelOf(teachers ? APPROVALS : STATUSES, teachers ? row.teacher_profile?.approval?.status : row.status)}</Status>{teachers && <small>{approvalSource(row.teacher_profile?.approval?.source)}</small>}</td><td>{row.email}<small>{row.email_verified ? 'Đã xác minh' : 'Chưa xác minh'}</small></td><td><button className="adm-text-button" onClick={() => setSelected(row.id)}>Xem hồ sơ</button></td></tr>)}</tbody></table></div></Feedback><Pagination offset={offset} count={resource.data?.count || 0} onChange={setOffset} /></div>
    {selected && <AccountDetail key={selected} userId={selected} currentUser={currentUser} capabilities={capabilities} onClose={() => setSelected(null)} onSaved={saved} />}
    {creating && capabilities.create_account && <CreateAccount onClose={() => setCreating(false)} onSaved={() => { setCreating(false); setOffset(0); saved() }} />}</>
}

function AccountDetail({ userId, currentUser, capabilities, onClose, onSaved }) {
  const detail = useAdminData(`users/${userId}/`)
  const user = detail.data
  const [mode, setMode] = useState(null)
  const [history, setHistory] = useState('')
  const approval = user?.teacher_profile?.approval
  const editable = capabilities.edit_account
  const actions = approval?.status === 'PENDING' ? [['APPROVED', 'Duyệt giảng dạy'], ['REJECTED', 'Từ chối']] : approval?.status === 'APPROVED' ? [['REVOKED', 'Thu hồi quyền']] : [['APPROVED', 'Duyệt lại']]
  const allowed = mode?.kind === 'approval' ? capabilities.decide_teacher : mode?.kind === 'role' ? capabilities.assign_role : editable
  return <Modal title="Hồ sơ tài khoản" onClose={onClose} wide><Feedback resource={detail}>{user && <><div className="adm-person"><span className="adm-person-avatar">{(user.full_name || user.username).slice(0, 1)}</span><div><h3>{user.full_name || user.username}</h3><p>@{user.username} · {labelOf(ROLES, user.role)}</p></div><Status tone={user.status === 'ACTIVE' ? 'good' : ''}>{labelOf(STATUSES, user.status)}</Status></div><dl className="adm-details"><div><dt>Email</dt><dd>{user.email} · {user.email_verified ? 'Đã xác minh' : 'Chưa xác minh'}</dd></div><div><dt>Số điện thoại</dt><dd>{user.phone || 'Chưa có'}</dd></div><div><dt>Ngày tham gia</dt><dd>{dateText(user.date_joined)}</dd></div>{user.role === 'TEACHER' && <><div><dt>Trường công tác</dt><dd>{user.teacher_profile?.institution?.name || user.teacher_profile?.institution_other_name || 'Chưa khai báo'}</dd></div><div><dt>Duyệt giảng dạy</dt><dd>{labelOf(APPROVALS, approval?.status)} · {approvalSource(approval?.source)}</dd></div><div><dt>Lý do gần nhất</dt><dd>{approval?.reason || 'Chưa có'}</dd></div></>}</dl>
      <div className="adm-action-strip">{editable && <button className="secondary-button" onClick={() => setMode({ kind: 'profile' })}>Sửa thông tin</button>}{editable && user.id !== currentUser.id && <button className="secondary-button" onClick={() => setMode({ kind: 'status' })}>Đổi trạng thái</button>}{capabilities.assign_role && user.id !== currentUser.id && <button className="secondary-button" onClick={() => setMode({ kind: 'role' })}>Đổi vai trò</button>}{capabilities.decide_teacher && user.role === 'TEACHER' && approval && actions.map(([status, text]) => <button className={status === 'APPROVED' ? 'solid-button' : 'secondary-button'} key={status} onClick={() => setMode({ kind: 'approval', status })}><ShieldCheck size={16} />{text}</button>)}</div>
      <div className="adm-action-strip">{capabilities.account_history && <button className="adm-text-button" onClick={() => setHistory(history === 'account' ? '' : 'account')}>Lịch sử tài khoản</button>}{capabilities.teacher_history && user.role === 'TEACHER' && <button className="adm-text-button" onClick={() => setHistory(history === 'approval' ? '' : 'approval')}>Lịch sử xét duyệt</button>}</div>
      {history && <History key={history} path={history === 'account' ? `users/${user.id}/history/` : `teachers/${user.id}/approval/history/`} />}
      {mode && allowed && <MutationForm key={`${mode.kind}-${mode.status || ''}-${user.updated_at}-${approval?.revision}`} user={user} mode={mode} onCancel={() => setMode(null)} onSaved={() => { setMode(null); detail.refresh(); onSaved() }} onConflict={() => { setMode(null); detail.refresh() }} />}</>}</Feedback></Modal>
}

function MutationForm({ user, mode, onCancel, onSaved, onConflict }) {
  const [values, setValues] = useState({ status: user.status, role: user.role, full_name: user.full_name, email: user.email, phone: user.phone, reason: '', current_password: '' })
  const [state, setState] = useState({ busy: false, error: '' })
  const lock = useRef(false)
  const set = (key, value) => setValues(old => ({ ...old, [key]: value }))
  async function save(event) {
    event.preventDefault()
    if (lock.current) return
    lock.current = true; setState({ busy: true, error: '' })
    const confirmation = { current_password: values.current_password, reason: values.reason }
    let path = `users/${user.id}/`, method = 'PATCH'
    let body = { ...confirmation, expected_updated_at: user.updated_at }
    if (mode.kind === 'approval') { path = `teachers/${user.id}/approval/`; method = 'POST'; body = { ...confirmation, status: mode.status, expected_revision: user.teacher_profile.approval.revision } }
    else if (mode.kind === 'role') { path += 'role/'; method = 'POST'; body.role = values.role }
    else if (mode.kind === 'status') body.status = values.status
    else for (const field of ['full_name', 'email', 'phone']) body[field] = values[field]
    try { await writeAdmin(path, body, method); onSaved() } catch (error) { setValues(old => ({ ...old, current_password: '' })); setState({ busy: false, error: adminError(error), conflict: error.status === 409 }) } finally { lock.current = false }
  }
  return <ValidatedForm className="adm-confirm-form" onSubmit={save}><h3>Xác nhận thay đổi · @{user.username}</h3><p>{mode.kind === 'approval' ? labelOf(APPROVALS, mode.status) : 'Kiểm tra đúng tài khoản trước khi lưu. Phiên cũ sẽ bị thu hồi khi khóa hoặc đổi vai trò.'}</p>{mode.kind === 'role' && <SelectField label="Vai trò mới" value={values.role} onChange={v => set('role', v)} options={ROLES} disabled={state.busy} />}{mode.kind === 'status' && <SelectField label="Trạng thái mới" value={values.status} onChange={v => set('status', v)} options={STATUSES} disabled={state.busy} />}{mode.kind === 'profile' && <div className="adm-form-grid">{[['full_name', 'Họ và tên'], ['email', 'Email'], ['phone', 'Số điện thoại']].map(([key, label]) => <Field key={key} label={label} type={key === 'email' ? 'email' : 'text'} required={key !== 'phone'} value={values[key] || ''} onChange={e => set(key, e.target.value)} disabled={state.busy} />)}</div>}<Field label="Lý do thay đổi" value={values.reason} maxLength={1000} required disabled={state.busy} onChange={e => set('reason', e.target.value)} /><Field label="Mật khẩu Admin của bạn" type="password" autoComplete="current-password" required value={values.current_password} disabled={state.busy} onChange={e => set('current_password', e.target.value)} />{state.error && <p className="error-banner" role="alert">{state.error}</p>}<div className="adm-action-strip">{state.conflict ? <button className="solid-button" type="button" onClick={onConflict}>Tải lại hồ sơ</button> : <button className="solid-button" disabled={state.busy}>{state.busy ? 'Đang lưu…' : 'Xác nhận và lưu'}</button>}<button type="button" className="secondary-button" disabled={state.busy} onClick={onCancel}>Hủy</button></div></ValidatedForm>
}

function History({ path }) {
  const [offset, setOffset] = useState(0)
  const resource = useAdminData(`${path}?offset=${offset}&limit=20`)
  return <section className="adm-history"><h3>Lịch sử thay đổi</h3><Feedback resource={resource} empty={!resource.data?.results?.length}><ol>{resource.data?.results.map(row => <li key={row.id}><strong>{auditAction(row.action || row.details?.action)}</strong><time>{dateText(row.created_at || row.action_time)}</time><p>{row.action === 'LEGACY_APPROVED' ? 'Giữ quyền giảng dạy của giáo viên đã có khi triển khai xét duyệt.' : row.reason || row.details?.reason}</p><small>{row.revision ? `Phiên bản ${row.revision}` : 'Đã ghi nhận thay đổi'}</small></li>)}</ol></Feedback><Pagination offset={offset} count={resource.data?.count || 0} onChange={setOffset} /></section>
}

function CreateAccount({ onClose, onSaved }) {
  const [values, setValues] = useState({ username: '', full_name: '', email: '', password: '', role: 'STUDENT', reason: '', current_password: '', institution_other_name: '' })
  const [institution, setInstitution] = useState(null)
  const [schoolError, setSchoolError] = useState('')
  const [state, setState] = useState({ busy: false, error: '' })
  const lock = useRef(false)
  const set = (key, value) => setValues(old => ({ ...old, [key]: value }))
  async function submit(e) {
    e.preventDefault(); if (lock.current) return
    lock.current = true; setState({ busy: true, error: '' })
    const body = { ...values }
    if (values.role === 'TEACHER' && institution?.id) { body.institution_id = institution.id; body.institution_other_name = '' }
    if (values.role !== 'TEACHER') delete body.institution_other_name
    try { await writeAdmin('users/', body); onSaved() } catch (error) { set('current_password', ''); setState({ busy: false, error: adminError(error) }) } finally { lock.current = false }
  }
  return <Modal title="Tạo tài khoản" busy={state.busy} onClose={onClose}><ValidatedForm onSubmit={submit} className="adm-form" validate={() => { const error = values.role === 'TEACHER' && !institution ? 'Vui lòng chọn trường đang công tác.' : ''; setSchoolError(error); return !error }}><div className="adm-form-grid">{[['username', 'Tên đăng nhập'], ['full_name', 'Họ và tên'], ['email', 'Email'], ['password', 'Mật khẩu ban đầu']].map(([key, label]) => <Field key={key} label={label} type={key === 'password' ? 'password' : key === 'email' ? 'email' : 'text'} autoComplete={key === 'password' ? 'new-password' : 'off'} required value={values[key]} disabled={state.busy} onChange={e => set(key, e.target.value)} />)}</div><SelectField label="Loại tài khoản" value={values.role} options={ROLES.slice(0, 2)} onChange={v => set('role', v)} disabled={state.busy} />{values.role === 'TEACHER' && <><InstitutionCombobox value={institution} error={schoolError} onChange={value => { setInstitution(value); setSchoolError('') }} disabled={state.busy} />{institution?.other && <Field label="Tên trường tự khai" required value={values.institution_other_name} onChange={e => set('institution_other_name', e.target.value)} disabled={state.busy} />}<p className="adm-info">Giáo viên mới ở trạng thái chờ duyệt. Email chưa được tự xác minh.</p></>}<Field label="Lý do tạo tài khoản" required maxLength={1000} value={values.reason} onChange={e => set('reason', e.target.value)} disabled={state.busy} /><Field label="Mật khẩu Admin của bạn" type="password" autoComplete="current-password" required value={values.current_password} onChange={e => set('current_password', e.target.value)} disabled={state.busy} />{state.error && <p className="error-banner" role="alert">{state.error}</p>}<button className="solid-button" disabled={state.busy}>{state.busy ? 'Đang tạo…' : 'Tạo tài khoản'}</button></ValidatedForm></Modal>
}
