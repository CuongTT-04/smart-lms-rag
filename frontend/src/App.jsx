import { useEffect, useRef, useState } from 'react'
import { LoaderCircle, Sun } from 'lucide-react'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import TeacherHomePage from './pages/TeacherHomePage'
import StudentHomePage from './pages/StudentHomePage'
import RegisterPage from './pages/RegisterPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import { currentUser, logout, authErrorMessage } from './services/auth.service'
import { clearAccessToken } from './services/api'

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  const publicPage = ['/register', '/forgot-password', '/reset-password'].includes(path)
  const [session, setSession] = useState({ checking: !publicPage, user: null, error: '' })
  const sessionRequestId = useRef(0)

  useEffect(() => {
    if (publicPage) return
    const controller = new AbortController()
    const requestId = ++sessionRequestId.current
    currentUser(controller.signal).then(
      (user) => {
        if (!controller.signal.aborted && requestId === sessionRequestId.current) {
          setSession({ checking: false, user, error: '' })
        }
      },
      (error) => {
        if (!controller.signal.aborted && requestId === sessionRequestId.current) {
          setSession({ checking: false, user: null, error: error.status === 401 ? '' : authErrorMessage(error) })
        }
      },
    )
    return () => controller.abort()
  }, [publicPage])

  function handleAuthenticated(user) {
    // Ignore any earlier bootstrap request that may finish after this login.
    sessionRequestId.current += 1
    setSession({ checking: false, user, error: '' })
  }

  function handleUserUpdated(user) {
    setSession((previous) => previous.user?.id === user.id ? { ...previous, user } : previous)
  }

  function handleSessionExpired(notice) {
    sessionRequestId.current += 1
    clearAccessToken()
    setSession({ checking: false, user: null, error: '', notice })
  }

  useEffect(() => {
    document.title = publicPage
      ? `OHAYO | ${{ '/register': 'Đăng ký', '/forgot-password': 'Quên mật khẩu', '/reset-password': 'Đặt mật khẩu mới' }[path]}`
      : session.user?.role === 'TEACHER'
      ? 'OHAYO | Không gian giảng dạy'
      : session.user?.role === 'STUDENT'
        ? 'OHAYO | Không gian học tập'
        : session.user ? 'OHAYO | Tài khoản' : 'OHAYO | Đăng nhập'
  }, [session.user, path, publicPage])

  async function handleLogout() {
    try {
      await logout()
      setSession({ checking: false, user: null, error: '' })
    } catch (error) {
      if (error.status === 401) {
        try { await currentUser() } catch (sessionError) {
          if (sessionError.status === 401) {
            setSession({ checking: false, user: null, error: '' })
            return
          }
        }
      }
      throw error
    }
  }

  if (session.checking) return <main className="session-loading" aria-live="polite"><Sun className="brand-sun" size={36} aria-hidden="true" /><strong>OHAYO</strong><span><LoaderCircle className="spin" size={18} aria-hidden="true" /> Đang kết nối...</span></main>
  if (path === '/register') return <RegisterPage />
  if (path === '/forgot-password') return <ForgotPasswordPage />
  if (path === '/reset-password') return <ResetPasswordPage />
  if (!session.user) return <LoginPage initialError={session.error} initialNotice={session.notice} onAuthenticated={handleAuthenticated} />
  const profileProps = { user: session.user, onLogout: handleLogout, onUserUpdated: handleUserUpdated, onSessionExpired: handleSessionExpired }
  if (session.user.role === 'TEACHER') return <TeacherHomePage {...profileProps} />
  if (session.user.role === 'STUDENT') return <StudentHomePage {...profileProps} />
  return <DashboardPage {...profileProps} />
}
