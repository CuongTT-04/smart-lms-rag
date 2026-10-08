import { useEffect, useRef, useState } from 'react'
import { AlertCircle, ArrowRight, BookOpen, CheckCircle2, GraduationCap, LoaderCircle, Mail, UserRound } from 'lucide-react'
import AuthLayout from '../components/AuthLayout'
import AuthField from '../components/AuthField'
import { passwordError, PASSWORD_REQUIREMENTS } from '../utils/password'
import { registerAccount, accountFieldErrors, accountErrorMessage } from '../services/auth.service'

export default function RegisterPage() {
  const [values, setValues] = useState({ full_name: '', username: '', email: '', password: '', password_confirm: '', role: '' })
  const [fields, setFields] = useState({})
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [created, setCreated] = useState(null)
  const submitting = useRef(false)
  const form = useRef(null)
  const focusTarget = useRef(null)

  useEffect(() => {
    if (!pending && focusTarget.current) {
      form.current?.querySelector(`[name="${focusTarget.current}"]`)?.focus()
      focusTarget.current = null
    }
  }, [fields, pending])

  function change(name, value) {
    setValues((previous) => ({ ...previous, [name]: value }))
    setFields((previous) => ({ ...previous, [name]: '' }))
    setError('')
  }

  function showFields(errors) {
    setFields(errors)
    const first = Object.keys(errors)[0]
    focusTarget.current = first
    form.current?.querySelector(`[name="${first}"]`)?.focus()
  }

  async function submit(event) {
    event.preventDefault()
    if (submitting.current) return
    const errors = {}
    if (!values.role) errors.role = 'Vui lòng chọn Học viên hoặc Giáo viên.'
    if (!values.full_name.trim()) errors.full_name = 'Vui lòng nhập họ và tên.'
    if (!values.username.trim()) errors.username = 'Vui lòng nhập tên đăng nhập.'
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(values.email.trim())) errors.email = 'Vui lòng nhập email hợp lệ.'
    if (passwordError(values.password)) errors.password = passwordError(values.password)
    if (!values.password_confirm || values.password_confirm !== values.password) errors.password_confirm = 'Mật khẩu xác nhận không khớp.'
    setError('')
    showFields(errors)
    if (Object.keys(errors).length) return
    submitting.current = true
    setPending(true)
    try {
      setCreated(await registerAccount(values))
      setValues((previous) => ({ ...previous, password: '', password_confirm: '' }))
    } catch (failure) {
      const errors = accountFieldErrors(failure)
      showFields(errors)
      setError(accountErrorMessage(failure))
    } finally { submitting.current = false; setPending(false) }
  }

  return <AuthLayout wide title={created ? 'Chào mừng đến OHAYO!' : 'Tạo tài khoản OHAYO'} intro={created ? undefined : 'Một khởi đầu mới cho hành trình tri thức của bạn.'}>
    {created ? <div className="auth-result" role="status">
      <CheckCircle2 size={40} aria-hidden="true" />
      <h2>Đăng ký thành công</h2>
      <p>Tài khoản {created.role === 'TEACHER' ? 'giáo viên' : 'học viên'} của bạn đã sẵn sàng. Hãy đăng nhập để bắt đầu.</p>
      <a className="primary-button" href="/">Đăng nhập ngay<ArrowRight size={19} aria-hidden="true" /></a>
    </div> : <>
      <form ref={form} className="login-form register-form" onSubmit={submit} noValidate aria-busy={pending}>
        <fieldset className="role-selector" disabled={pending} aria-describedby={fields.role ? 'role-error' : undefined}>
          <legend>Bạn là</legend>
          <div className="role-options">
            {[['STUDENT', 'Học viên', BookOpen], ['TEACHER', 'Giáo viên', GraduationCap]].map(([role, label, Icon]) => <label className={`role-option ${values.role === role ? 'selected' : ''}`} key={role}>
              <input type="radio" name="role" value={role} checked={values.role === role} onChange={() => change('role', role)} required aria-invalid={Boolean(fields.role)} />
              <Icon size={21} aria-hidden="true" /><span>{label}</span>
            </label>)}
          </div>
          {fields.role && <p className="field-error" id="role-error">{fields.role}</p>}
        </fieldset>
        <div className="auth-field-grid">
          <AuthField name="full_name" label="Họ và tên" icon={UserRound} autoComplete="name" maxLength={255} placeholder="Nguyễn Minh Anh" value={values.full_name} onChange={(e) => change('full_name', e.target.value)} error={fields.full_name} pending={pending} />
          <AuthField name="username" label="Tên đăng nhập" icon={UserRound} autoComplete="username" autoCapitalize="none" spellCheck={false} maxLength={150} placeholder="minhanh" value={values.username} onChange={(e) => change('username', e.target.value)} error={fields.username} pending={pending} />
        </div>
        <AuthField name="email" label="Email" icon={Mail} type="email" autoComplete="email" maxLength={254} placeholder="ban@example.com" value={values.email} onChange={(e) => change('email', e.target.value)} error={fields.email} pending={pending} />
        <div className="auth-field-grid">
          <AuthField name="password" label="Mật khẩu" password hint={PASSWORD_REQUIREMENTS} autoComplete="new-password" maxLength={128} placeholder="Mật khẩu" value={values.password} onChange={(e) => change('password', e.target.value)} error={fields.password} pending={pending} />
          <AuthField name="password_confirm" label="Xác nhận mật khẩu" password autoComplete="new-password" maxLength={128} placeholder="Nhập lại mật khẩu" value={values.password_confirm} onChange={(e) => change('password_confirm', e.target.value)} error={fields.password_confirm} pending={pending} />
        </div>
        {error && <div className="error-banner" role="alert"><AlertCircle size={18} aria-hidden="true" /><span>{error}</span></div>}
        <button className="primary-button" disabled={pending} type="submit">{pending ? 'Đang tạo tài khoản' : 'Đăng ký'}{pending ? <LoaderCircle className="spin" size={19} aria-hidden="true" /> : <ArrowRight size={19} aria-hidden="true" />}</button>
      </form>
      <div className="login-help"><span>Đã có tài khoản?</span><a href="/">Đăng nhập</a></div>
    </>}
  </AuthLayout>
}
