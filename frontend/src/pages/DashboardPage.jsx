import { useState } from 'react'
import { AlertCircle, Check, LoaderCircle, LogOut, Sun } from 'lucide-react'
import { authErrorMessage } from '../services/auth.service'
import ProfileEditor from '../components/ProfileEditor'


export default function DashboardPage({ user, onLogout, onUserUpdated, onSessionExpired }) {
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  async function handleLogout() {
    if (pending) return
    setPending(true)
    setError('')
    try { await onLogout() } catch (requestError) { setError(authErrorMessage(requestError)) } finally { setPending(false) }
  }
  return (
    <main className="account-page">
      <header className="account-header"><span className="wordmark"><Sun className="brand-sun" size={31} aria-hidden="true" /> OHAYO<span className="brand-period">.</span></span><button className="secondary-button" type="button" disabled={pending} onClick={handleLogout}>{pending ? <LoaderCircle className="spin" size={18} /> : <LogOut size={18} />} Đăng xuất</button></header>
      <section className="account-content" aria-labelledby="account-title">
        <span className="welcome-note"><Check size={16} aria-hidden="true" /> ĐĂNG NHẬP THÀNH CÔNG</span>
        <h1 id="account-title">Xin chào, {user.full_name || user.username}!</h1>
        <p className="account-intro">Chào mừng bạn đến với OHAYO.</p>
        <ProfileEditor user={user} onUserUpdated={onUserUpdated} onSessionExpired={onSessionExpired} />
        {error && <div className="error-banner" role="alert"><AlertCircle size={19} aria-hidden="true" />{error}</div>}
      </section>
      <footer className="account-footer">© {new Date().getFullYear()} OHAYO</footer>
    </main>
  )
}
