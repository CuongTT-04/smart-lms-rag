import { useEffect, useRef, useState } from 'react'
import { AlertCircle, ArrowRight, CheckCircle2, LoaderCircle, ShieldCheck } from 'lucide-react'
import AuthLayout from '../components/AuthLayout'
import AuthField from '../components/AuthField'
import { passwordError, PASSWORD_REQUIREMENTS } from '../utils/password'
import { confirmPasswordReset, accountFieldErrors, accountErrorMessage } from '../services/auth.service'

export default function ResetPasswordPage() {
  const [link] = useState(() => {
    const query = new URLSearchParams(window.location.search)
    return { uid: query.get('uid') || '', token: query.get('token') || '' }
  })
  const [values, setValues] = useState({ password: '', password_confirm: '' })
  const [fields, setFields] = useState({})
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [done, setDone] = useState(false)
  const [invalidLink, setInvalidLink] = useState(!link.uid || !link.token || link.uid.length > 128 || link.token.length > 128)
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

  async function submit(event) {
    event.preventDefault()
    if (submitting.current || invalidLink) return
    const errors = {}
    if (passwordError(values.password)) errors.password = passwordError(values.password)
    if (!values.password_confirm || values.password !== values.password_confirm) errors.password_confirm = 'Mật khẩu xác nhận không khớp.'
    setFields(errors)
    focusTarget.current = Object.keys(errors)[0]
    setError('')
    if (Object.keys(errors).length) {
      form.current?.querySelector(`[name="${Object.keys(errors)[0]}"]`)?.focus()
      return
    }
    submitting.current = true
    setPending(true)
    try {
      await confirmPasswordReset({ ...link, ...values })
      setValues({ password: '', password_confirm: '' })
      window.history.replaceState(null, '', window.location.pathname)
      setDone(true)
    } catch (failure) {
      const errors = accountFieldErrors(failure)
      if (errors.token || errors.uid) setInvalidLink(true)
      else {
        setFields(errors)
        focusTarget.current = Object.keys(errors)[0]
        form.current?.querySelector(`[name="${Object.keys(errors)[0]}"]`)?.focus()
        setError(accountErrorMessage(failure))
      }
    } finally { submitting.current = false; setPending(false) }
  }

  return <AuthLayout title={done ? 'Sẵn sàng trở lại' : invalidLink ? 'Liên kết không khả dụng' : 'Đặt mật khẩu mới'} intro={!done && !invalidLink ? 'Một mật khẩu mới, một khởi đầu an tâm.' : undefined}>
    {done ? <div className="auth-result" role="status">
      <CheckCircle2 size={40} aria-hidden="true" /><h2>Đổi mật khẩu thành công</h2>
      <p>Bạn có thể đăng nhập bằng mật khẩu mới. Các phiên đăng nhập cũ đã được vô hiệu hóa.</p>
      <a className="primary-button" href="/">Đăng nhập ngay<ArrowRight size={19} aria-hidden="true" /></a>
    </div> : invalidLink ? <div className="auth-result invalid-link" role="alert">
      <ShieldCheck size={40} aria-hidden="true" /><h2>Yêu cầu một liên kết mới</h2>
      <p>Liên kết không hợp lệ, đã hết hạn hoặc đã được sử dụng.</p>
      <a className="primary-button" href="/forgot-password" referrerPolicy="no-referrer">Gửi liên kết mới<ArrowRight size={19} aria-hidden="true" /></a>
    </div> : <form ref={form} className="login-form" onSubmit={submit} noValidate aria-busy={pending}>
      <AuthField name="password" label="Mật khẩu mới" password hint={PASSWORD_REQUIREMENTS} autoComplete="new-password" maxLength={128} placeholder="Nhập mật khẩu mới" value={values.password} error={fields.password} pending={pending} onChange={(e) => change('password', e.target.value)} />
      <AuthField name="password_confirm" label="Xác nhận mật khẩu" password autoComplete="new-password" maxLength={128} placeholder="Nhập lại mật khẩu mới" value={values.password_confirm} error={fields.password_confirm} pending={pending} onChange={(e) => change('password_confirm', e.target.value)} />
      {error && <div className="error-banner" role="alert"><AlertCircle size={18} aria-hidden="true" /><span>{error}</span></div>}
      <button className="primary-button" type="submit" disabled={pending}>{pending ? 'Đang cập nhật' : 'Lưu mật khẩu mới'}{pending ? <LoaderCircle size={19} className="spin" aria-hidden="true" /> : <ArrowRight size={19} aria-hidden="true" />}</button>
    </form>}
  </AuthLayout>
}
