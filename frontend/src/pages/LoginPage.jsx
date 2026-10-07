import { useRef, useState } from 'react'
import { AlertCircle, ArrowRight, Check, Eye, EyeOff, LockKeyhole, LoaderCircle, Sun, UserRound } from 'lucide-react'
import { login, authErrorMessage } from '../services/auth.service'

export default function LoginPage({ onAuthenticated, initialError = '', initialNotice = '' }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [visible, setVisible] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState(initialError)
  const [notice, setNotice] = useState(initialNotice)
  const [fields, setFields] = useState({})
  const submitting = useRef(false)
  const usernameInput = useRef(null)
  const passwordInput = useRef(null)

  async function handleSubmit(event) {
    event.preventDefault()
    if (submitting.current) return
    const errors = {}
    if (!username.trim()) errors.username = 'Vui lòng nhập tên đăng nhập.'
    if (!password) errors.password = 'Vui lòng nhập mật khẩu.'
    setFields(errors)
    setError('')
    setNotice('')
    if (Object.keys(errors).length) {
      const input = errors.username ? usernameInput : passwordInput
      input.current?.focus()
      return
    }
    submitting.current = true
    setPending(true)
    try {
      const user = await login(username, password)
      setPassword('')
      onAuthenticated(user)
    } catch (requestError) { setError(authErrorMessage(requestError)) }
    finally { submitting.current = false; setPending(false) }
  }

  return (
    <main className="login-shell">
      <img className="library-backdrop" src="/ohayo-library.png" alt="" fetchPriority="high" />
      <div className="login-surface">
        <header className="login-header">
          <a className="wordmark" href="/" aria-label="OHAYO, trang đăng nhập"><Sun size={31} className="brand-sun" aria-hidden="true" />OHAYO<span className="brand-period">.</span></a>
          <span className="header-caption">Hệ thống quản lý học tập thông minh</span>
        </header>
        <section className="login-content" aria-labelledby="login-title">
          <h1 id="login-title">Một khởi đầu mới.<br /><span>Chào bạn trở lại!</span></h1>
          <p className="login-intro">Đăng nhập để tiếp tục hành trình học tập của bạn.</p>
          <form className="login-form" onSubmit={handleSubmit} noValidate aria-busy={pending}>
            {notice && <div className="success-banner" role="status"><Check size={18} aria-hidden="true" />{notice}</div>}
            <div className="form-field">
              <label htmlFor="username">Tên đăng nhập</label>
              <div className={`input-wrap ${fields.username ? 'input-invalid' : ''}`}>
                <UserRound size={19} aria-hidden="true" />
                <input ref={usernameInput} id="username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} maxLength={150} placeholder="Nhập tên đăng nhập" value={username} onChange={(event) => { setUsername(event.target.value); setFields((previous) => ({ ...previous, username: '' })) }} disabled={pending} aria-invalid={Boolean(fields.username)} aria-describedby={fields.username ? 'username-error' : undefined} />
              </div>
              {fields.username && <p className="field-error" id="username-error">{fields.username}</p>}
            </div>
            <div className="form-field">
              <label htmlFor="password">Mật khẩu</label>
              <div className={`input-wrap ${fields.password ? 'input-invalid' : ''}`}>
                <LockKeyhole size={19} aria-hidden="true" />
                <input ref={passwordInput} id="password" name="password" type={visible ? 'text' : 'password'} autoComplete="current-password" placeholder="Nhập mật khẩu" value={password} onChange={(event) => { setPassword(event.target.value); setFields((previous) => ({ ...previous, password: '' })) }} disabled={pending} aria-invalid={Boolean(fields.password)} aria-describedby={fields.password ? 'password-error' : undefined} />
                <button className="icon-button password-toggle" type="button" onClick={() => setVisible((previous) => !previous)} aria-label={visible ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'} title={visible ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'} aria-pressed={visible} disabled={pending}>{visible ? <EyeOff size={19} /> : <Eye size={19} />}</button>
              </div>
              {fields.password && <p className="field-error" id="password-error">{fields.password}</p>}
            </div>
            {error && <div className="error-banner" role="alert"><AlertCircle size={19} aria-hidden="true" /><span>{error}</span></div>}
            <a className="forgot-link" href="/forgot-password">Quên mật khẩu?</a>
            <button className="primary-button login-submit" type="submit" disabled={pending}>{pending ? <>Đang đăng nhập<LoaderCircle size={19} className="spin" aria-hidden="true" /></> : <>Đăng nhập<ArrowRight size={20} aria-hidden="true" /></>}</button>
          </form>
          <div className="login-help"><span>Chưa có tài khoản?</span><a href="/register">Đăng ký</a></div>
        </section>
        <footer className="login-footer"><span>© {new Date().getFullYear()} OHAYO</span></footer>
      </div>
      <aside className="photo-caption" aria-label="Thông điệp OHAYO"><span className="photo-eyebrow">MỖI NGÀY, MỘT ĐIỀU MỚI</span><p>Tri thức bắt đầu<br />từ sự tò mò.</p><span className="photo-caption-line" /></aside>
    </main>
  )
}
