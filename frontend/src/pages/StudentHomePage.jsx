import { useEffect, useMemo, useState } from 'react'
import {
  AlertCircle, ArrowLeft, BookOpen, Check, ChevronRight, CircleUserRound,
  GraduationCap, Home, LayoutGrid, LoaderCircle, LogOut, Menu, Search, Sun, X,
} from 'lucide-react'
import { authErrorMessage } from '../services/auth.service'
import ProfileEditor from '../components/ProfileEditor'
import UserAvatar from '../components/UserAvatar'
import HeaderProfile from '../components/HeaderProfile'
import { courseErrorMessage, getCourse, listAllCourses } from '../services/course.service'

function formatDate(value) {
  if (!value) return 'Chưa cập nhật'
  return new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(value))
}


function firstName(name) {
  return (name || '').trim().split(/\s+/).at(-1) || 'bạn'
}

function PublishedBadge() {
  return <span className="course-status status-published"><span />Đã xuất bản</span>
}

function EmptyCourses() {
  return <div className="student-empty"><GraduationCap size={34} aria-hidden="true" /><h3>Chưa có khóa học</h3><p>Khi được giáo viên cấp quyền, các khóa học phù hợp sẽ xuất hiện ở đây.</p></div>
}

export default function StudentHomePage({ user, onLogout, onUserUpdated, onSessionExpired }) {
  const [view, setView] = useState('overview')
  const [courses, setCourses] = useState([])
  const [selectedCourse, setSelectedCourse] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [mobileNav, setMobileNav] = useState(false)
  const [pendingLogout, setPendingLogout] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    listAllCourses(controller.signal)
      .then((courseList) => {
        if (!controller.signal.aborted) setCourses(courseList)
      })
      .catch((requestError) => {
        if (!controller.signal.aborted) setError(courseErrorMessage(requestError))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [])

  const filteredCourses = useMemo(() => courses.filter((course) => (
    `${course.title} ${course.description || ''}`.toLocaleLowerCase('vi').includes(search.trim().toLocaleLowerCase('vi'))
  )), [courses, search])

  function navigate(nextView) {
    setView(nextView)
    setSelectedId(null)
    setSelectedCourse(null)
    setMobileNav(false)
    setError('')
  }

  async function openCourse(course) {
    setView('courses')
    setSelectedId(course.id)
    setSelectedCourse(null)
    setDetailLoading(true)
    setMobileNav(false)
    setError('')
    try {
      setSelectedCourse(await getCourse(course.id))
    } catch (requestError) {
      setError(courseErrorMessage(requestError))
    } finally {
      setDetailLoading(false)
    }
  }

  async function handleLogout() {
    if (pendingLogout) return
    setPendingLogout(true)
    try { await onLogout() } catch (requestError) { setError(authErrorMessage(requestError)) } finally { setPendingLogout(false) }
  }

  return (
    <main className="student-app">
      <aside className={`student-sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
        <div className="sidebar-brand"><Sun size={31} className="brand-sun" aria-hidden="true" />OHAYO<span className="brand-period">.</span></div>
        <nav aria-label="Điều hướng học viên">
          <button className={view === 'overview' ? 'active' : ''} type="button" onClick={() => navigate('overview')}><Home size={19} /> Tổng quan</button>
          <button className={view === 'courses' ? 'active' : ''} type="button" onClick={() => navigate('courses')}><BookOpen size={19} /> Khóa học của tôi</button>
          <button className={view === 'account' ? 'active' : ''} type="button" onClick={() => navigate('account')}><CircleUserRound size={19} /> Tài khoản</button>
        </nav>
        <div className="sidebar-profile"><UserAvatar user={user} /><span><strong>{user.full_name || user.username}</strong><small>Học viên</small></span><button className="icon-button" type="button" title="Đăng xuất" aria-label="Đăng xuất" disabled={pendingLogout} onClick={handleLogout}>{pendingLogout ? <LoaderCircle className="spin" size={18} /> : <LogOut size={18} />}</button></div>
      </aside>
      {mobileNav && <button className="nav-backdrop" type="button" aria-label="Đóng menu" onClick={() => setMobileNav(false)} />}

      <div className="student-main">
        <header className="student-topbar">
          <button className="icon-button mobile-menu" type="button" aria-label="Mở menu" onClick={() => setMobileNav(true)}><Menu size={22} /></button>
          <div><span className="topbar-eyebrow">KHÔNG GIAN HỌC TẬP</span><strong>{view === 'overview' ? 'Tổng quan' : view === 'courses' ? 'Khóa học của tôi' : 'Tài khoản'}</strong></div>
          <HeaderProfile user={user} onAccount={() => navigate('account')} />
        </header>

        <div className="student-content">
          {error && <div className="error-banner page-message" role="alert"><AlertCircle size={19} />{error}<button className="icon-button" aria-label="Đóng thông báo" onClick={() => setError('')}><X size={17} /></button></div>}
          {loading ? <div className="dashboard-loading"><LoaderCircle className="spin" size={24} /> Đang tải không gian học tập...</div> : (
            <>
              {view === 'overview' && <Overview user={user} courses={courses} onCourses={() => navigate('courses')} onOpen={openCourse} />}
              {view === 'courses' && !selectedId && <CoursesView courses={filteredCourses} search={search} setSearch={setSearch} onOpen={openCourse} />}
              {view === 'courses' && selectedId && <CourseDetail course={selectedCourse} loading={detailLoading} onBack={() => { setSelectedId(null); setSelectedCourse(null) }} />}
              {view === 'account' && <ProfileEditor user={user} onUserUpdated={onUserUpdated} onSessionExpired={onSessionExpired} logoutPending={pendingLogout} onLogout={handleLogout} />}
            </>
          )}
        </div>
      </div>
    </main>
  )
}

function Overview({ user, courses, onCourses, onOpen }) {
  const statItems = [
    { label: 'Khóa học của tôi', value: courses.length, icon: LayoutGrid, tone: 'green' },
    { label: 'Sẵn sàng học', value: courses.length, icon: BookOpen, tone: 'coral' },
    { label: 'Đã xuất bản', value: courses.length, icon: Check, tone: 'blue' },
  ]
  return <section className="student-view" aria-labelledby="student-welcome">
    <div className="student-welcome"><div><span className="welcome-note"><span className="note-line" /> CHÀO MỪNG TRỞ LẠI</span><h1 id="student-welcome">Chào {firstName(user.full_name || user.username)}!</h1><p>{courses.length > 0 ? `Bạn đang có ${courses.length} khóa học sẵn sàng để khám phá.` : 'Không gian học tập của bạn đang chờ khóa học đầu tiên.'}</p></div><button className="solid-button" type="button" onClick={onCourses}><BookOpen size={18} /> Xem khóa học</button></div>
    <div className="student-stats-grid">{statItems.map(({ label, value, icon: Icon, tone }) => <article className="student-stat-card" key={label}><span className={`stat-icon ${tone}`}><Icon size={20} /></span><div><strong>{value}</strong><span>{label}</span></div></article>)}</div>
    <section className="student-section"><div className="section-heading"><div><h2>Tiếp tục với khóa học</h2><p>Các khóa học giáo viên đã cấp quyền cho bạn.</p></div>{courses.length > 0 && <button className="text-button" type="button" onClick={onCourses}>Xem tất cả <ChevronRight size={17} /></button>}</div>
      {courses.length === 0 ? <EmptyCourses /> : <div className="student-course-grid">{courses.slice(0, 3).map((course) => <CourseCard course={course} key={course.id} onOpen={() => onOpen(course)} />)}</div>}
    </section>
  </section>
}

function CoursesView({ courses, search, setSearch, onOpen }) {
  return <section className="student-view" aria-labelledby="student-courses-title">
    <div className="page-title"><div><span className="welcome-note"><BookOpen size={16} /> KHO KHÓA HỌC</span><h1 id="student-courses-title">Khóa học của tôi</h1><p>Chọn một khóa học để xem thông tin được giáo viên công bố.</p></div></div>
    <div className="student-course-toolbar"><label className="search-field"><Search size={18} /><span className="sr-only">Tìm khóa học</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tìm theo tên hoặc mô tả..." /></label><span>{courses.length} khóa học</span></div>
    {courses.length === 0 ? (search ? <div className="student-empty"><Search size={32} /><h3>Không tìm thấy khóa học</h3><p>Thử thay đổi từ khóa tìm kiếm của bạn.</p></div> : <EmptyCourses />) : <div className="student-course-grid full">{courses.map((course) => <CourseCard course={course} key={course.id} onOpen={() => onOpen(course)} />)}</div>}
  </section>
}

function CourseCard({ course, onOpen }) {
  return <article className="student-course-card"><div className="student-course-icon"><BookOpen size={23} /></div><div className="student-course-card-content"><PublishedBadge /><h3>{course.title}</h3><p>{course.description || 'Giáo viên chưa thêm mô tả cho khóa học này.'}</p></div><div className="student-course-card-footer"><span>Cập nhật {formatDate(course.updated_at)}</span><button className="outline-button" type="button" onClick={onOpen}>Xem khóa học <ChevronRight size={17} /></button></div></article>
}

function CourseDetail({ course, loading, onBack }) {
  if (loading) return <div className="dashboard-loading"><LoaderCircle className="spin" size={24} /> Đang mở khóa học...</div>
  if (!course) return <section className="student-detail"><button className="back-button" type="button" onClick={onBack}><ArrowLeft size={18} /> Quay lại danh sách</button></section>
  return <section className="student-detail" aria-labelledby="student-course-detail-title"><button className="back-button" type="button" onClick={onBack}><ArrowLeft size={18} /> Quay lại danh sách</button><div className="student-detail-hero"><div className="student-detail-icon"><GraduationCap size={27} /></div><div><PublishedBadge /><h1 id="student-course-detail-title">{course.title}</h1><p>{course.description || 'Giáo viên chưa thêm mô tả cho khóa học này.'}</p></div></div><section className="student-information"><div className="student-information-heading"><BookOpen size={20} /><div><h2>Thông tin khóa học</h2><p>Nội dung chi tiết, bài học và tiến độ sẽ xuất hiện ở đây khi giáo viên công bố.</p></div></div><dl><div><dt>Trạng thái</dt><dd><PublishedBadge /></dd></div><div><dt>Ngày xuất bản</dt><dd>{formatDate(course.published_at || course.updated_at)}</dd></div><div><dt>Cập nhật gần nhất</dt><dd>{formatDate(course.updated_at)}</dd></div></dl></section></section>
}
