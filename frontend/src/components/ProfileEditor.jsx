import { useEffect, useRef, useState } from 'react'
import { AlertCircle, Check, CircleUserRound, LoaderCircle, LogOut, Save, ShieldCheck, Trash2, Upload, X } from 'lucide-react'
import AuthField from './AuthField'
import UserAvatar from './UserAvatar'
import { updateProfile, uploadAvatar, profileErrors } from '../services/profile.service'
import { passwordError, PASSWORD_REQUIREMENTS } from '../utils/password'

const ROLES = { STUDENT: 'Học viên', TEACHER: 'Giáo viên', ADMIN: 'Quản trị viên' }
const IDENTITY = ['full_name', 'username', 'email', 'phone', 'avatar_url']

function draftOf(user) {
  return Object.fromEntries([...IDENTITY, 'learning_goal', 'bio', 'specialization'].map((key) => [key, user[key] ?? user.student_profile?.[key] ?? user.teacher_profile?.[key] ?? '']))
}

const emptyPasswords = () => ({ current_password: '', password: '', password_confirm: '' })

export default function ProfileEditor({ user, onUserUpdated, onSessionExpired, onLogout, logoutPending = false }) {
  const [tab, setTab] = useState('identity')
  const [draft, setDraft] = useState(() => draftOf(user))
  const [passwords, setPasswords] = useState(emptyPasswords)
  const [fields, setFields] = useState({})
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState('')
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState('')
  const fileInput = useRef(null)
  const form = useRef(null)
  const busy = useRef(false)
  const focusTarget = useRef(null)
  const roleFields = user.role === 'STUDENT' ? ['learning_goal'] : user.role === 'TEACHER' ? ['bio', 'specialization'] : []
  const emailChanged = draft.email.trim().toLowerCase() !== (user.email || '').toLowerCase()
  const disabled = Boolean(pending) || logoutPending

  useEffect(() => {
    return () => { if (preview) URL.revokeObjectURL(preview) }
  }, [preview])

  useEffect(() => {
    if (!pending && focusTarget.current) {
      form.current?.querySelector(`[name="${focusTarget.current}"]`)?.focus()
      focusTarget.current = null
    }
  }, [fields, pending])

  function showFields(errors) {
    setFields(errors)
    focusTarget.current = Object.keys(errors)[0]
  }

  function change(key, value, secret = false) {
    const setter = secret ? setPasswords : setDraft
    setter((previous) => ({ ...previous, [key]: value }))
    setFields((previous) => ({ ...previous, [key]: '' }))
    setError(''); setNotice('')
  }

  function switchTab(next) {
    setTab(next); setFields({}); setError(''); setNotice(''); setPasswords(emptyPasswords())
  }

  function failed(failure) {
    if ([401, 403].includes(failure.status)) {
      onSessionExpired?.('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.')
      return
    }
    const result = profileErrors(failure)
    showFields(result.fields); setError(result.message)
  }

  async function save(event) {
    event.preventDefault()
    if (busy.current) return
    const errors = {}
    let changes
    const names = tab === 'identity' ? IDENTITY : roleFields
    if (tab === 'security') {
      if (!passwords.current_password) errors.current_password = 'Vui lòng nhập mật khẩu hiện tại.'
      if (passwordError(passwords.password)) errors.password = passwordError(passwords.password)
      if (!passwords.password_confirm || passwords.password_confirm !== passwords.password) errors.password_confirm = 'Mật khẩu xác nhận không khớp.'
      changes = passwords
    } else {
      const original = draftOf(user)
      const changed = Object.fromEntries(names.filter((name) => draft[name] !== original[name]).map((name) => [name, draft[name]]))
      if (!Object.keys(changed).length) { setNotice('Chưa có thay đổi để lưu.'); return }
      if (tab === 'identity') {
        if ('username' in changed && !draft.username.trim()) errors.username = 'Vui lòng nhập tên đăng nhập.'
        if ('full_name' in changed && !draft.full_name.trim()) errors.full_name = 'Vui lòng nhập họ và tên.'
        if ('email' in changed && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.email.trim())) errors.email = 'Vui lòng nhập email hợp lệ.'
        if (draft.phone && !/^\+?[0-9]{8,15}$/.test(draft.phone)) errors.phone = 'Số điện thoại cần 8–15 chữ số, có thể bắt đầu bằng dấu +.'
        if (draft.avatar_url && !/^https?:\/\//i.test(draft.avatar_url)) errors.avatar_url = 'Vui lòng nhập đường dẫn ảnh hợp lệ.'
        changes = { ...changed, ...(emailChanged ? { current_password: passwords.current_password } : {}) }
        if (emailChanged && !passwords.current_password) errors.current_password = 'Vui lòng nhập mật khẩu hiện tại để đổi email.'
      } else changes = { [user.role === 'STUDENT' ? 'student_profile' : 'teacher_profile']: changed }
    }
    showFields(errors); setError(''); setNotice('')
    if (Object.keys(errors).length) return
    busy.current = true; setPending('save')
    try {
      const result = await updateProfile(changes)
      setPasswords(emptyPasswords())
      if (result.requires_login) onSessionExpired?.('Đổi mật khẩu thành công. Vui lòng đăng nhập lại.')
      else {
        onUserUpdated?.(result.user)
        const updated = draftOf(result.user)
        setDraft((previous) => ({ ...previous, ...Object.fromEntries(names.map((name) => [name, updated[name]])) }))
        setNotice('Đã lưu thay đổi.')
      }
    } catch (failure) { failed(failure) }
    finally { busy.current = false; setPending('') }
  }

  function cancelFile() {
    setFile(null); setPreview('')
    if (fileInput.current) fileInput.current.value = ''
  }

  function chooseFile(event) {
    const selected = event.target.files?.[0]
    if (!selected) return
    setError(''); setNotice('')
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(selected.type) || selected.size > 5 * 1024 * 1024) {
      cancelFile(); setFields({ avatar: 'Vui lòng chọn ảnh JPG, PNG hoặc WebP không quá 5 MB.' }); return
    }
    setFields({}); setFile(selected); setPreview(URL.createObjectURL(selected))
  }

  async function saveAvatar(remove = false) {
    if (busy.current || (!remove && !file)) return
    busy.current = true; setPending('avatar'); setError(''); setNotice(''); setFields({})
    try {
      const updated = remove ? (await updateProfile({ avatar_url: '' })).user : await uploadAvatar(file)
      onUserUpdated?.(updated)
      setDraft((previous) => ({ ...previous, avatar_url: updated.avatar_url || '' }))
      cancelFile(); setNotice(remove ? 'Đã xóa ảnh đại diện.' : 'Đã cập nhật ảnh đại diện.')
    } catch (failure) { failed(failure) }
    finally { busy.current = false; setPending('') }
  }

  function input(name, label, options = {}) {
    const secret = ['current_password', 'password', 'password_confirm'].includes(name)
    return <AuthField key={name} name={name} label={label} value={secret ? passwords[name] : draft[name]} pending={disabled}
      error={fields[name]} onChange={(e) => change(name, e.target.value, secret)} required={false} {...options} />
  }

  function textarea(name, label) {
    return <div className="form-field"><label htmlFor={name}>{label}</label><textarea id={name} name={name} rows={5} maxLength={5000} value={draft[name]} disabled={disabled}
      onChange={(e) => change(name, e.target.value)} aria-invalid={Boolean(fields[name])} aria-describedby={fields[name] ? `${name}-error` : undefined} />
      {fields[name] && <p className="field-error" id={`${name}-error`}>{fields[name]}</p>}</div>
  }

  return <section className="account-view profile-editor" aria-labelledby="profile-title">
    <span className="welcome-note"><CircleUserRound size={16} aria-hidden="true" />HỒ SƠ {user.role === 'TEACHER' ? 'GIÁO VIÊN' : user.role === 'STUDENT' ? 'HỌC VIÊN' : 'TÀI KHOẢN'}</span>
    <h1 id="profile-title">Tài khoản của bạn</h1>
    <div className="profile-identity">
      <UserAvatar user={user} className="large-avatar" preview={preview} />
      <div><h2>{user.full_name || user.username}</h2><div className="profile-role"><span>{ROLES[user.role]}</span><span>· {user.status === 'ACTIVE' ? 'Đang hoạt động' : 'Chưa hoạt động'}</span></div>
        <div className="avatar-actions">
          <input ref={fileInput} className="sr-only" id="avatar-file" type="file" accept="image/jpeg,image/png,image/webp" aria-label="Chọn ảnh đại diện từ máy" onChange={chooseFile} disabled={disabled} />
          <button type="button" className="outline-button" disabled={disabled} onClick={() => fileInput.current?.click()}><Upload size={16} />Tải ảnh lên</button>
          {file ? <><button className="solid-button" type="button" disabled={disabled} onClick={() => saveAvatar()}>{pending === 'avatar' ? <LoaderCircle className="spin" size={16} /> : <Check size={16} />}Lưu ảnh</button><button className="icon-button" type="button" disabled={disabled} aria-label="Hủy chọn ảnh" title="Hủy chọn ảnh" onClick={cancelFile}><X size={18} /></button></>
            : user.avatar_url && <button className="icon-button" type="button" disabled={disabled} onClick={() => saveAvatar(true)} aria-label="Xóa ảnh đại diện" title="Xóa ảnh đại diện"><Trash2 size={17} /></button>}
        </div>
      </div>
    </div>
    {file && <p className="avatar-filename">{file.name}</p>}
    {fields.avatar && <p className="field-error" role="alert">{fields.avatar}</p>}
    {error && <div className="error-banner" role="alert"><AlertCircle size={18} />{error}</div>}
    {notice && <div className="success-banner profile-notice" role="status"><Check size={18} />{notice}</div>}
    <div className="profile-tabs" role="tablist" aria-label="Quản lý tài khoản">
      {[['identity', 'Thông tin chung'], ...(roleFields.length ? [['profile', 'Hồ sơ']] : []), ['security', 'Bảo mật']].map(([key, label]) => <button key={key} type="button" role="tab" id={`tab-${key}`} aria-selected={tab === key} aria-controls="profile-panel" disabled={disabled} onClick={() => switchTab(key)}>{label}</button>)}
    </div>
    <form ref={form} id="profile-panel" role="tabpanel" aria-labelledby={`tab-${tab}`} className="profile-form" onSubmit={save} noValidate aria-busy={Boolean(pending)}>
      {tab === 'identity' && <>
        <div className="profile-field-grid">{input('full_name', 'Họ và tên', { maxLength: 255, autoComplete: 'name' })}{input('username', 'Tên đăng nhập', { maxLength: 150, autoComplete: 'username', autoCapitalize: 'none', spellCheck: false })}</div>
        <div className="profile-field-grid">{input('email', 'Email', { type: 'email', maxLength: 254, autoComplete: 'email' })}{input('phone', 'Số điện thoại', { type: 'tel', maxLength: 20, autoComplete: 'tel' })}</div>
        {input('avatar_url', 'Đường dẫn ảnh đại diện', { type: 'url', maxLength: 2048 })}
        {emailChanged && input('current_password', 'Mật khẩu hiện tại', { password: true, autoComplete: 'current-password', maxLength: 128 })}
      </>}
      {tab === 'profile' && (user.role === 'STUDENT' ? textarea('learning_goal', 'Mục tiêu học tập') : <>{textarea('bio', 'Giới thiệu')}{input('specialization', 'Chuyên môn', { maxLength: 255 })}</>)}
      {tab === 'security' && <>
        <h2 className="profile-section-title"><ShieldCheck size={20} />Đổi mật khẩu</h2>
        {input('current_password', 'Mật khẩu hiện tại', { password: true, autoComplete: 'current-password', maxLength: 128 })}
        {input('password', 'Mật khẩu mới', { password: true, hint: PASSWORD_REQUIREMENTS, autoComplete: 'new-password', maxLength: 128 })}
        {input('password_confirm', 'Xác nhận mật khẩu', { password: true, autoComplete: 'new-password', maxLength: 128 })}
      </>}
      <div className="profile-save"><button className="solid-button" type="submit" disabled={disabled}>{pending === 'save' ? <LoaderCircle className="spin" size={18} /> : <Save size={18} />}{tab === 'security' ? 'Đổi mật khẩu' : 'Lưu thay đổi'}</button></div>
    </form>
    {onLogout && <div className="profile-logout"><button className="outline-button danger-outline" disabled={disabled} onClick={onLogout}>{logoutPending ? <LoaderCircle className="spin" size={18} /> : <LogOut size={18} />}Đăng xuất khỏi OHAYO</button></div>}
  </section>
}
