import { useEffect, useRef, useState } from 'react'
import { ArrowRight, CheckCircle2, Mail } from 'lucide-react'
import AuthLayout from '../components/AuthLayout'
import { accountErrorMessage, confirmEmailVerification } from '../services/auth.service'

export default function VerifyEmailPage() {
  const [token] = useState(() => new URLSearchParams(window.location.search).get('token') || '')
  const [state, setState] = useState({ busy: false, done: false, error: '' })
  const pending = useRef(false)
  const valid = token.length > 0 && token.length <= 256
  useEffect(() => { window.history.replaceState(null, '', '/verify-email') }, [])

  async function confirm() {
    if (!valid || pending.current || state.done) return
    pending.current = true
    setState({ busy: true, done: false, error: '' })
    try {
      await confirmEmailVerification(token)
      setState({ busy: false, done: true, error: '' })
    } catch (error) {
      setState({ busy: false, done: false, error: error.status === 400
        ? 'Liên kết không hợp lệ, đã hết hạn hoặc đã được sử dụng.' : accountErrorMessage(error) })
    } finally { pending.current = false }
  }

  return <AuthLayout title="Xác minh email">
    <div className="auth-result">
      {state.done ? <CheckCircle2 size={36} aria-hidden="true" /> : <Mail size={36} aria-hidden="true" />}
      <p>{state.done ? 'Email đã được xác minh. Đăng nhập để xem trạng thái xét duyệt mới nhất.'
        : valid ? 'Xác nhận địa chỉ email đăng ký tài khoản OHAYO của bạn.' : 'Liên kết thiếu mã xác minh. Vui lòng mở lại liên kết trong email.'}</p>
      {state.error && <div className="error-banner" role="alert">{state.error}</div>}
      {!state.done && valid && <button type="button" className="primary-button" disabled={state.busy} onClick={confirm}>{state.busy ? 'Đang xác minh…' : 'Xác minh email'}</button>}
      {state.done && <p role="status">Xác minh email thành công.</p>}
      <a href="/" className={state.done ? 'primary-button' : 'text-button'}>Đăng nhập<ArrowRight size={18} aria-hidden="true" /></a>
    </div>
  </AuthLayout>
}
