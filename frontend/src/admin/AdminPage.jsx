import { useEffect, useRef, useState } from 'react'
import { Activity, Building2, ChevronRight, CircleUserRound, LayoutDashboard, LogOut, Menu, ShieldCheck, Sun, UsersRound, X } from 'lucide-react'
import { useHistoryState } from '../hooks/useHistoryState'
import HeaderProfile from '../components/HeaderProfile'
import ProfileEditor from '../components/ProfileEditor'
import { authErrorMessage } from '../services/auth.service'
import useAdminData from './hooks/useAdminData'
import { Feedback } from './components/AdminControls'
import OverviewPage from './pages/OverviewPage'
import AccountsPage from './pages/AccountsPage'
import InstitutionsPage from './pages/InstitutionsPage'
import OperationsPage from './pages/OperationsPage'
import './admin.css'

const NAV = [['overview', 'Tổng quan', LayoutDashboard], ['accounts', 'Tài khoản', UsersRound], ['teachers', 'Duyệt giáo viên', ShieldCheck], ['institutions', 'Danh mục trường', Building2], ['operations', 'Vận hành', Activity]]

export default function AdminPage({ user, onLogout, onUserUpdated, onSessionExpired }) {
  const [view, setView] = useHistoryState('admin.view', 'overview')
  const [filters, setFilters] = useState({})
  const [mobile, setMobile] = useState(false)
  const sidebar = useRef(null)
  const menuButton = useRef(null)
  const main = useRef(null)
  useEffect(() => {
    if (!mobile) return
    const media = typeof window.matchMedia === 'function' ? window.matchMedia('(max-width: 760px)') : null
    const content = main.current
    const opener = menuButton.current
    const previousOverflow = document.body.style.overflow
    let restoreFocus = true
    document.body.style.overflow = 'hidden'
    content.inert = true
    sidebar.current.querySelector('button')?.focus()
    function keyboard(event) {
      if (event.key === 'Escape') { event.preventDefault(); setMobile(false) }
      if (event.key !== 'Tab') return
      const controls = [...sidebar.current.querySelectorAll('a[href],button:not(:disabled)')].filter(node => node.getClientRects().length)
      const first = controls[0], last = controls.at(-1)
      if (!first) return
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    function viewportChange(event) {
      if (!event.matches) {
        restoreFocus = false
        setMobile(false)
      }
    }
    document.addEventListener('keydown', keyboard)
    if (media?.addEventListener) media.addEventListener('change', viewportChange)
    else media?.addListener?.(viewportChange)
    return () => {
      document.body.style.overflow = previousOverflow
      content.inert = false
      document.removeEventListener('keydown', keyboard)
      if (media?.removeEventListener) media.removeEventListener('change', viewportChange)
      else media?.removeListener?.(viewportChange)
      if (restoreFocus) opener?.focus()
    }
  }, [mobile])
  const [logoutState, setLogoutState] = useState({ busy: false, error: '' })
  const resource = useAdminData('capabilities/')
  const refreshCapabilities = resource.refresh
  const capabilities = resource.data && resource.data.user_id === user.id ? resource.data.capabilities : {}
  useEffect(() => {
    const refresh = () => { if (!document.hidden) refreshCapabilities() }
    window.addEventListener('focus', refresh)
    window.addEventListener('ohayo:admin-permissions-changed', refresh)
    const timer = setInterval(refresh, 60000)
    return () => { window.removeEventListener('focus', refresh); window.removeEventListener('ohayo:admin-permissions-changed', refresh); clearInterval(timer) }
  }, [refreshCapabilities])
  function openMobile() {
    if (typeof window.matchMedia === 'function' && !window.matchMedia('(max-width: 760px)').matches) return
    setMobile(true)
  }
  function navigate(target, nextFilters = {}) { setFilters(nextFilters); setView(target); setMobile(false) }
  async function logout() {
    if (logoutState.busy) return
    setLogoutState({ busy: true, error: '' })
    try { await onLogout() } catch (error) { setLogoutState({ busy: false, error: authErrorMessage(error) }) }
  }
  const current = NAV.find(([key]) => key === view)?.[1] || 'Hồ sơ cá nhân'
  return <div className="adm-shell"><a href="#admin-content" className="adm-skip">Đến nội dung chính</a>
    <aside ref={sidebar} id="admin-navigation" className={`adm-sidebar ${mobile ? 'open' : ''}`} aria-label="Điều hướng quản trị"><a href="/" className="wordmark"><Sun className="brand-sun" size={29} />OHAYO<span className="brand-period">.</span></a><span className="adm-workspace-label">KHÔNG GIAN QUẢN TRỊ</span><button className="adm-mobile-close" aria-label="Đóng điều hướng" onClick={() => setMobile(false)}><X size={20} /></button><nav>{NAV.filter(([key]) => capabilities[key]).map(([key, text, Icon]) => <button key={key} aria-current={view === key ? 'page' : undefined} onClick={() => navigate(key)}><Icon size={19} /><span>{text}</span>{view === key && <ChevronRight size={16} />}</button>)}</nav><div className="adm-sidebar-bottom"><button onClick={() => navigate('profile')} aria-current={view === 'profile' ? 'page' : undefined}><CircleUserRound size={19} />Hồ sơ cá nhân</button><button onClick={logout} disabled={logoutState.busy}><LogOut size={19} />{logoutState.busy ? 'Đang đăng xuất…' : 'Đăng xuất'}</button></div></aside>
    {mobile && <button className="adm-nav-shade" aria-label="Thu gọn điều hướng" onClick={() => setMobile(false)} />}
    <div ref={main} className="adm-main"><header className="adm-topbar"><button ref={menuButton} className="adm-menu-button" aria-label="Mở điều hướng" aria-expanded={mobile} aria-controls="admin-navigation" onClick={openMobile}><Menu size={22} /></button><div><span>Quản trị hệ thống</span><ChevronRight size={14} /><strong>{current}</strong></div><HeaderProfile user={user} onAccount={() => navigate('profile')} /></header><main id="admin-content" className="adm-content" tabIndex={-1}><div key={view} className="adm-view-enter">{logoutState.error && <p className="error-banner" role="alert">{logoutState.error}</p>}{view === 'profile' ? <><div className="adm-page-heading"><div><p className="adm-eyebrow">TÀI KHOẢN CỦA BẠN</p><h1>Hồ sơ cá nhân</h1></div></div><section className="adm-panel"><ProfileEditor user={user} onUserUpdated={onUserUpdated} onSessionExpired={onSessionExpired} /></section></> : <Feedback resource={resource}>{!capabilities[view] ? <section className="adm-panel adm-state"><ShieldCheck size={32} /><h1>Chưa có quyền truy cập</h1><p>Chọn một mục được cấp quyền trên thanh điều hướng hoặc liên hệ quản trị viên phụ trách.</p></section> : <>{view === 'overview' && <OverviewPage onNavigate={navigate} capabilities={capabilities} />}{(view === 'accounts' || view === 'teachers') && <AccountsPage key={`${view}-${JSON.stringify(filters)}`} initialFilters={filters} teachers={view === 'teachers'} capabilities={capabilities} currentUser={user} />}{view === 'institutions' && <InstitutionsPage capabilities={capabilities} />}{view === 'operations' && <OperationsPage />}</>}</Feedback>}</div></main><footer className="adm-footer">OHAYO · Không gian quản trị</footer></div></div>
}
