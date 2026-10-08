import { useEffect, useState } from 'react'
import { currentUser, logout } from '../services/auth.service'
import { listAllCourses } from '../services/course.service'
import LoginPage from './LoginPage'
import CourseDocuments from '../components/documents/CourseDocuments'

export default function DocumentsPage() {
  const [user, setUser] = useState(null)
  const [ready, setReady] = useState(false)
  const [courses, setCourses] = useState([])
  const [courseId, setCourseId] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    currentUser(controller.signal).then((account) => { if (!controller.signal.aborted) setUser(account) })
      .catch(() => { if (!controller.signal.aborted) setError('Vui lòng đăng nhập để mở học liệu.') })
      .finally(() => { if (!controller.signal.aborted) setReady(true) })
    return () => controller.abort()
  }, [])
  useEffect(() => {
    if (!user) return
    const controller = new AbortController()
    listAllCourses(controller.signal).then((rows) => { if (!controller.signal.aborted) { setCourses(rows); setCourseId(rows[0]?.id || '') } })
      .catch(() => { if (!controller.signal.aborted) setError('Không thể tải danh sách khóa học.') })
    return () => controller.abort()
  }, [user])
  async function signOut() {
    try { await logout() } finally { setUser(null); setCourses([]); setCourseId('') }
  }
  if (!ready) return <p role="status">Đang kiểm tra đăng nhập…</p>
  if (!user) return <LoginPage onAuthenticated={(account) => { setUser(account); setError('') }} initialError={error} />
  return <main className="documents-page"><header><div><h1>Học liệu khóa học</h1><p>{user.full_name || user.username}</p></div><nav><a className="outline-button" href="/">Trang chính</a><button className="outline-button" onClick={signOut}>Đăng xuất</button></nav></header>
    {error && <p role="alert" className="error-banner">{error}</p>}
    <label>Khóa học<select value={courseId} onChange={(event) => setCourseId(event.target.value)}>{courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</select></label>
    {courseId ? <CourseDocuments key={courseId} courseId={courseId} canManage={user.role === 'TEACHER'} /> : <p>Chưa có khóa học được cấp quyền truy cập.</p>}
  </main>
}
