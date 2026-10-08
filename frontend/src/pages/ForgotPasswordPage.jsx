import { useEffect, useRef, useState } from 'react'
import { AlertCircle, ArrowRight, LoaderCircle, Mail, MailCheck } from 'lucide-react'
import AuthLayout from '../components/AuthLayout'
import AuthField from '../components/AuthField'
import { requestPasswordReset, passwordResetPath, accountErrorMessage } from '../services/auth.service'

export default function ForgotPasswordPage({ onNavigate = (url) => window.location.assign(url) }) {
  const [email, setEmail] = useState('')
  const [fieldError, setFieldError] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [sent, setSent] = useState(false)
  const submitting = useRef(false)
  const form = useRef(null)

  useEffect(() => {
    if (!pending && fieldError) form.current?.querySelector('input')?.focus()
  }, [fieldError, pending])

  async function submit(event) {
    event.preventDefault()
    if (submitting.current) return
    setError('')
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setFieldError('Vui lòng nhập email hợp lệ.')
      form.current?.querySelector('input')?.focus()
      return
    }
    setFieldError('')
    submitting.current = true
    setPending(true)
    try {
      const result = await requestPasswordReset(email)
      if (result.reset_url) onNavigate(passwordResetPath(result.reset_url))
      else setSent(true)
    }
    catch (failure) {
      if (failure.status === 400 && failure.data?.email) setFieldError('Vui lòng nhập email hợp lệ.')
      setError(accountErrorMessage(failure))
    } finally { submitting.current = false; setPending(false) }
  }

  return <AuthLayout title={sent ? 'Kiểm tra hộp thư' : 'Quên mật khẩu?'} intro={sent ? undefined : 'Đừng lo, bạn có thể bắt đầu lại.'}>
    {sent ? <div className="auth-result" role="status">
      <MailCheck size={40} aria-hidden="true" />
      <h2>Yêu cầu đã được tiếp nhận</h2>
      <p>Nếu email <strong>{email.trim()}</strong> thuộc tài khoản hợp lệ, bạn sẽ nhận được liên kết đặt lại mật khẩu. Hãy kiểm tra cả thư mục spam.</p>
      <a className="primary-button" href="/">Quay lại đăng nhập<ArrowRight size={19} aria-hidden="true" /></a>
      <button className="auth-text-button" type="button" onClick={() => { setSent(false); setError('') }}>Nhập email khác</button>
    </div> : <form ref={form} className="login-form" onSubmit={submit} noValidate aria-busy={pending}>
      <AuthField name="email" label="Email tài khoản" icon={Mail} type="email" autoComplete="email" maxLength={254} placeholder="ban@example.com" value={email} pending={pending} error={fieldError} onChange={(e) => { setEmail(e.target.value); setFieldError(''); setError('') }} />
      {error && <div className="error-banner" role="alert"><AlertCircle size={18} aria-hidden="true" /><span>{error}</span></div>}
      <button className="primary-button" disabled={pending} type="submit">{pending ? 'Đang gửi yêu cầu' : 'Gửi liên kết đặt lại'}{pending ? <LoaderCircle size={19} className="spin" aria-hidden="true" /> : <ArrowRight size={19} aria-hidden="true" />}</button>
    </form>}
  </AuthLayout>
}
