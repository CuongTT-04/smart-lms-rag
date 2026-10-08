import { useEffect, useMemo, useState } from 'react'
import CustomSelect from '../components/CustomSelect'
import CourseDocuments from '../components/documents/CourseDocuments'
import {
  AlertCircle, ArrowLeft, BookOpen, Check, ChevronRight, CircleUserRound,
  FilePenLine, Home, LayoutGrid, LoaderCircle, LogOut, Menu,
  MoreHorizontal, Plus, RefreshCw, Search, Send, Sun, UserMinus, UsersRound, X,
} from 'lucide-react'
import { authErrorMessage } from '../services/auth.service'
import ProfileEditor from '../components/ProfileEditor'
import UserAvatar from '../components/UserAvatar'
import HeaderProfile from '../components/HeaderProfile'
import { TeacherEnrollmentPanel } from '../components/EnrollmentPanels'
import {
  courseErrorMessage, createCourse, listAllCourseMembers,
  listAllCourses, revokeStudentAccess, updateCourse,
} from '../services/course.service'

const STATUS = {
  DRAFT: { label: 'Bản nháp', className: 'status-draft' },
  PUBLISHED: { label: 'Đã xuất bản', className: 'status-published' },
  ARCHIVED: { label: 'Đã lưu trữ', className: 'status-archived' },
}
const MEMBER_STATUS = {
  ACTIVE: 'Đang tham gia', SUSPENDED: 'Tạm dừng', REMOVED: 'Đã thu hồi',
}
const MEMBER_ROLE = { OWNER: 'Chủ khóa học', TEACHER: 'Đồng giảng cũ', ASSISTANT: 'Trợ giảng cũ', STUDENT: 'Học viên' }

function formatDate(value) {
  if (!value) return 'Chưa cập nhật'
  return new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(value))
}

function initials(name) {
  return (name || 'GV').trim().split(/\s+/).slice(-2).map((part) => part[0]).join('').toUpperCase()
}

function StatusBadge({ status }) {
  const info = STATUS[status] || { label: status, className: '' }
  return <span className={`course-status ${info.className}`}><span />{info.label}</span>
}

function EmptyState({ onCreate }) {
  return <div className="teacher-empty"><BookOpen size={34} aria-hidden="true" /><h3>Chưa có khóa học nào</h3><p>Tạo khóa học đầu tiên để bắt đầu xây dựng lớp học của bạn.</p><button className="solid-button" type="button" onClick={onCreate}><Plus size={18} /> Tạo khóa học</button></div>
}

export default function TeacherHomePage({ user, onLogout, onUserUpdated, onSessionExpired }) {
  const [view, setView] = useState('overview')
  const [courses, setCourses] = useState([])
  const [members, setMembers] = useState({})
  const [selectedId, setSelectedId] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('ALL')
  const [createOpen, setCreateOpen] = useState(false)
  const [mobileNav, setMobileNav] = useState(false)
  const [pendingLogout, setPendingLogout] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    listAllCourses(controller.signal)
      .then(async (courseList) => {
        const memberResults = await Promise.allSettled(courseList.map((course) => listAllCourseMembers(course.id, controller.signal)))
        if (!controller.signal.aborted) {
          setCourses(courseList)
          setMembers(Object.fromEntries(courseList.map((course, index) => [
            course.id, memberResults[index].status === 'fulfilled' ? memberResults[index].value : [],
          ])))
        }
      })
      .catch((requestError) => {
        if (!controller.signal.aborted) setError(courseErrorMessage(requestError))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
    return () => controller.abort()
  }, [])

  const selectedCourse = courses.find((course) => course.id === selectedId)
  const filteredCourses = useMemo(() => courses.filter((course) => {
    const matchesText = `${course.title} ${course.description}`.toLocaleLowerCase('vi').includes(search.trim().toLocaleLowerCase('vi'))
    return matchesText && (filter === 'ALL' || course.status === filter)
  }), [courses, search, filter])
  const stats = useMemo(() => {
    const studentIds = new Set(Object.values(members).flat().filter((member) => member.role === 'STUDENT' && member.status === 'ACTIVE').map((member) => member.user.id))
    return {
      total: courses.length,
      published: courses.filter((course) => course.status === 'PUBLISHED').length,
      draft: courses.filter((course) => course.status === 'DRAFT').length,
      students: studentIds.size,
    }
  }, [courses, members])

  function openCourse(courseId) {
    setSelectedId(courseId)
    setView('courses')
    setMobileNav(false)
    setNotice('')
  }

  async function refreshMembers(courseId) {
    const data = await listAllCourseMembers(courseId)
    setMembers((current) => ({ ...current, [courseId]: data }))
  }

  function replaceCourse(course) {
    setCourses((current) => current.map((item) => item.id === course.id ? course : item))
  }

  async function handleLogout() {
    if (pendingLogout) return
    setPendingLogout(true)
    try { await onLogout() } catch (requestError) { setError(authErrorMessage(requestError)) } finally { setPendingLogout(false) }
  }

  function navigate(nextView) {
    setView(nextView)
    setSelectedId(null)
    setMobileNav(false)
    setError('')
    setNotice('')
  }

  return (
    <main className="teacher-app">
      <aside className={`teacher-sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
        <div className="sidebar-brand"><Sun size={31} className="brand-sun" aria-hidden="true" />OHAYO<span className="brand-period">.</span></div>
        <nav aria-label="Điều hướng giáo viên">
          <button className={view === 'overview' ? 'active' : ''} type="button" onClick={() => navigate('overview')}><Home size={19} /> Tổng quan</button>
          <button className={view === 'courses' ? 'active' : ''} type="button" onClick={() => navigate('courses')}><BookOpen size={19} /> Khóa học</button>
          <button className={view === 'account' ? 'active' : ''} type="button" onClick={() => navigate('account')}><CircleUserRound size={19} /> Tài khoản</button>
        </nav>
        <div className="sidebar-profile"><UserAvatar user={user} /><span><strong>{user.full_name || user.username}</strong><small>Giáo viên</small></span><button className="icon-button" type="button" title="Đăng xuất" aria-label="Đăng xuất" disabled={pendingLogout} onClick={handleLogout}>{pendingLogout ? <LoaderCircle className="spin" size={18} /> : <LogOut size={18} />}</button></div>
      </aside>
      {mobileNav && <button className="nav-backdrop" type="button" aria-label="Đóng menu" onClick={() => setMobileNav(false)} />}

      <div className="teacher-main">
        <header className="teacher-topbar">
          <button className="icon-button mobile-menu" type="button" aria-label="Mở menu" onClick={() => setMobileNav(true)}><Menu size={22} /></button>
          <div><span className="topbar-eyebrow">KHÔNG GIAN GIẢNG DẠY</span><strong>{view === 'overview' ? 'Tổng quan' : view === 'courses' ? 'Khóa học' : 'Tài khoản'}</strong></div>
          <HeaderProfile user={user} onAccount={() => navigate('account')} />
        </header>

        <div className="teacher-content">
          {error && <div className="error-banner page-message" role="alert"><AlertCircle size={19} />{error}<button className="icon-button" aria-label="Đóng thông báo" onClick={() => setError('')}><X size={17} /></button></div>}
          {notice && <div className="success-banner page-message" role="status"><Check size={18} />{notice}<button className="icon-button" aria-label="Đóng thông báo" onClick={() => setNotice('')}><X size={17} /></button></div>}
          {loading ? <div className="dashboard-loading"><LoaderCircle className="spin" size={24} /> Đang tải không gian giảng dạy...</div> : (
            <>
              {view === 'overview' && <Overview user={user} courses={courses} members={members} stats={stats} onCreate={() => setCreateOpen(true)} onSeeAll={() => navigate('courses')} onOpen={openCourse} />}
              {view === 'courses' && !selectedCourse && <CoursesView courses={filteredCourses} members={members} search={search} setSearch={setSearch} filter={filter} setFilter={setFilter} onCreate={() => setCreateOpen(true)} onOpen={openCourse} />}
              {view === 'courses' && selectedCourse && <CourseDetail course={selectedCourse} members={members[selectedCourse.id] || []} onBack={() => setSelectedId(null)} onUpdated={(course, message) => { replaceCourse(course); setNotice(message) }} onRefreshMembers={() => refreshMembers(selectedCourse.id)} onError={(message) => setError(message)} onNotice={setNotice} />}
              {view === 'account' && <ProfileEditor user={user} onUserUpdated={onUserUpdated} onSessionExpired={onSessionExpired} logoutPending={pendingLogout} onLogout={handleLogout} />}
            </>
          )}
        </div>
      </div>
      {createOpen && <CreateCourseModal onClose={() => setCreateOpen(false)} onCreated={(course) => { setCourses((current) => [course, ...current]); setMembers((current) => ({ ...current, [course.id]: [] })); setCreateOpen(false); setNotice('Đã tạo khóa học mới.'); openCourse(course.id) }} />}
    </main>
  )
}

function Overview({ user, courses, members, stats, onCreate, onSeeAll, onOpen }) {
  const statItems = [
    { label: 'Tổng khóa học', value: stats.total, icon: LayoutGrid, tone: 'green' },
    { label: 'Đã xuất bản', value: stats.published, icon: Send, tone: 'coral' },
    { label: 'Bản nháp', value: stats.draft, icon: FilePenLine, tone: 'gold' },
    { label: 'Học viên', value: stats.students, icon: UsersRound, tone: 'blue' },
  ]
  return <section className="dashboard-view" aria-labelledby="teacher-welcome">
    <div className="dashboard-welcome"><div><span className="welcome-note"><span className="note-line" /> CHÀO NGÀY MỚI</span><h1 id="teacher-welcome">Xin chào, {user.full_name || user.username}!</h1><p>Đây là tình hình lớp học của bạn hôm nay.</p></div><button className="solid-button" type="button" onClick={onCreate}><Plus size={18} /> Tạo khóa học</button></div>
    <div className="stats-grid">{statItems.map(({ label, value, icon: Icon, tone }) => <article className="stat-card" key={label}><span className={`stat-icon ${tone}`}><Icon size={20} /></span><div><strong>{value}</strong><span>{label}</span></div></article>)}</div>
    <section className="dashboard-section"><div className="section-heading"><div><h2>Khóa học gần đây</h2><p>Truy cập nhanh các lớp học bạn đang phụ trách.</p></div>{courses.length > 0 && <button className="text-button" type="button" onClick={onSeeAll}>Xem tất cả <ChevronRight size={17} /></button>}</div>
      {courses.length === 0 ? <EmptyState onCreate={onCreate} /> : <div className="course-list">{courses.slice(0, 4).map((course) => <CourseRow key={course.id} course={course} members={members[course.id] || []} onOpen={() => onOpen(course.id)} />)}</div>}
    </section>
  </section>
}

function CoursesView({ courses, members, search, setSearch, filter, setFilter, onCreate, onOpen }) {
  return <section className="dashboard-view" aria-labelledby="courses-title">
    <div className="page-title"><div><span className="welcome-note"><BookOpen size={16} /> QUẢN LÝ NỘI DUNG</span><h1 id="courses-title">Khóa học của tôi</h1><p>Tạo, cập nhật và quản lý quyền truy cập khóa học.</p></div><button className="solid-button" type="button" onClick={onCreate}><Plus size={18} /> Tạo khóa học</button></div>
    <div className="course-toolbar"><label className="search-field"><Search size={18} /><span className="sr-only">Tìm khóa học</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tìm theo tên hoặc mô tả..." /></label><div className="filter-tabs" aria-label="Lọc trạng thái">{[['ALL', 'Tất cả'], ['PUBLISHED', 'Đã xuất bản'], ['DRAFT', 'Bản nháp'], ['ARCHIVED', 'Lưu trữ']].map(([value, label]) => <button className={filter === value ? 'active' : ''} key={value} type="button" onClick={() => setFilter(value)}>{label}</button>)}</div></div>
    {courses.length === 0 ? <div className="teacher-empty"><Search size={32} /><h3>Không tìm thấy khóa học</h3><p>Thử thay đổi từ khóa hoặc bộ lọc trạng thái.</p></div> : <div className="course-list detailed">{courses.map((course) => <CourseRow key={course.id} course={course} members={members[course.id] || []} onOpen={() => onOpen(course.id)} />)}</div>}
  </section>
}

function CourseRow({ course, members = [], onOpen }) {
  const activeStudents = members.filter((member) => member.role === 'STUDENT' && member.status === 'ACTIVE').length
  return <article className="course-row"><div className="course-cover" aria-hidden="true"><BookOpen size={22} /></div><div className="course-summary"><div><StatusBadge status={course.status} /><span className="course-date">Cập nhật {formatDate(course.updated_at)}</span></div><h3>{course.title}</h3><p>{course.description || 'Chưa có mô tả cho khóa học này.'}</p></div><div className="course-meta"><span><UsersRound size={17} /> {activeStudents} học viên</span><button className="outline-button" type="button" onClick={onOpen}>Quản lý <ChevronRight size={17} /></button></div></article>
}

function CreateCourseModal({ onClose, onCreated }) {
  const [values, setValues] = useState({ title: '', description: '' })
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  async function submit(event) {
    event.preventDefault()
    if (!values.title.trim()) { setError('Vui lòng nhập tên khóa học.'); return }
    setPending(true); setError('')
    try { onCreated(await createCourse({ title: values.title.trim(), description: values.description })) }
    catch (requestError) { setError(courseErrorMessage(requestError)); setPending(false) }
  }
  return <div className="modal-layer" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}><section className="form-modal" role="dialog" aria-modal="true" aria-labelledby="create-course-title"><button className="icon-button modal-close" type="button" onClick={onClose} aria-label="Đóng"><X size={20} /></button><span className="modal-icon"><Plus size={22} /></span><h2 id="create-course-title">Tạo khóa học mới</h2><p>Khóa học được tạo ở trạng thái bản nháp.</p><form onSubmit={submit}><label>Tên khóa học <span>*</span><input autoFocus maxLength={255} value={values.title} onChange={(event) => setValues({ ...values, title: event.target.value })} placeholder="Ví dụ: Lập trình Python căn bản" /></label><label>Mô tả<textarea rows="4" value={values.description} onChange={(event) => setValues({ ...values, description: event.target.value })} placeholder="Giới thiệu ngắn về nội dung khóa học" /></label>{error && <div className="error-banner" role="alert"><AlertCircle size={18} />{error}</div>}<div className="modal-actions"><button className="outline-button" type="button" onClick={onClose}>Hủy</button><button className="solid-button" disabled={pending} type="submit">{pending ? <LoaderCircle className="spin" size={18} /> : <Plus size={18} />} Tạo khóa học</button></div></form></section></div>
}

function CourseDetail({ course, members, onBack, onUpdated, onRefreshMembers, onError, onNotice }) {
  const [tab, setTab] = useState('info')
  const [values, setValues] = useState({ title: course.title, description: course.description, status: course.status })
  const [pending, setPending] = useState(false)
  const [memberPending, setMemberPending] = useState('')
  async function save(event) {
    event.preventDefault(); setPending(true)
    try { const updated = await updateCourse(course.id, { title: values.title.trim(), description: values.description, status: values.status }); onUpdated(updated, 'Đã cập nhật khóa học.') }
    catch (requestError) { onError(courseErrorMessage(requestError)) }
    finally { setPending(false) }
  }
  async function revoke(member) {
    setMemberPending(member.id)
    try { await revokeStudentAccess(course.id, member.id); await onRefreshMembers(); onNotice(`Đã thu hồi quyền của ${member.user.full_name || member.user.username}.`) }
    catch (requestError) { onError(courseErrorMessage(requestError)) }
    finally { setMemberPending('') }
  }
  return <section className="course-detail" aria-labelledby="course-detail-title"><button className="back-button" type="button" onClick={onBack}><ArrowLeft size={18} /> Quay lại danh sách</button><div className="detail-header"><div><StatusBadge status={course.status} /><h1 id="course-detail-title">{course.title}</h1><p>{course.description || 'Chưa có mô tả cho khóa học này.'}</p></div><button className="icon-button" type="button" title="Làm mới thành viên" aria-label="Làm mới thành viên" onClick={onRefreshMembers}><RefreshCw size={18} /></button></div><div className="detail-tabs"><button className={tab === 'info' ? 'active' : ''} onClick={() => setTab('info')}>Thông tin khóa học</button><button className={tab === 'members' ? 'active' : ''} onClick={() => setTab('members')}>Thành viên <span>{members.length}</span></button><button className={tab === 'materials' ? 'active' : ''} onClick={() => setTab('materials')}>Học liệu</button><button className={tab === 'classrooms' ? 'active' : ''} onClick={() => setTab('classrooms')}>Lớp học</button><button className={tab === 'requests' ? 'active' : ''} onClick={() => setTab('requests')}>Yêu cầu tham gia</button></div>
    {tab === 'materials' && <CourseDocuments key={course.id} courseId={course.id} canManage />}
    {(tab === 'classrooms' || tab === 'requests') && <TeacherEnrollmentPanel key={course.id + tab} course={course} requestsOnly={tab === 'requests'} onMembersChanged={onRefreshMembers} />}
    {tab === 'info' && <form className="course-form" onSubmit={save}><div className="form-section-heading"><FilePenLine size={20} /><div><h2>Thông tin chung</h2><p>Chỉnh sửa nội dung và trạng thái hiển thị.</p></div></div><label>Tên khóa học<input maxLength={255} required value={values.title} onChange={(event) => setValues({ ...values, title: event.target.value })} /></label><label>Mô tả<textarea rows="6" value={values.description} onChange={(event) => setValues({ ...values, description: event.target.value })} /></label><label>Trạng thái<CustomSelect aria-label="Trạng thái" value={values.status} onChange={(event) => setValues({ ...values, status: event.target.value })}><option value="DRAFT">Bản nháp</option><option value="PUBLISHED">Đã xuất bản</option><option value="ARCHIVED">Đã lưu trữ</option></CustomSelect></label><div className="form-save"><span>Cập nhật gần nhất: {formatDate(course.updated_at)}</span><button className="solid-button" type="submit" disabled={pending}>{pending ? <LoaderCircle className="spin" size={18} /> : <Check size={18} />} Lưu thay đổi</button></div></form>}
    {tab === 'members' && <div className="members-panel"><div className="member-list"><div className="member-list-head"><h2>Thành viên toàn khóa học</h2><span>{members.filter((member) => member.status === 'ACTIVE').length} đang hoạt động</span></div>{members.length === 0 ? <div className="teacher-empty compact"><UsersRound size={30} /><h3>Chưa có thành viên</h3></div> : members.map((member) => <div className="member-row" key={member.id}><span className="member-avatar">{initials(member.user.full_name || member.user.username)}</span><div><strong>{member.user.full_name || member.user.username}</strong><span>{member.user.email || member.user.username}</span></div><span className="member-role">{MEMBER_ROLE[member.role] || member.role}</span><span className={`member-state state-${member.status.toLowerCase()}`}>{MEMBER_STATUS[member.status] || member.status}</span>{member.role === 'STUDENT' && member.status !== 'REMOVED' ? <button className="revoke-button course-revoke-button" title="Thu hồi quyền tham gia toàn bộ khóa học" type="button" disabled={memberPending === member.id} onClick={() => revoke(member)}>{memberPending === member.id ? <LoaderCircle className="spin" size={16} /> : <UserMinus size={16} />} <span>Thu hồi cả khóa</span></button> : <span className="member-menu"><MoreHorizontal size={18} /></span>}</div>)}</div></div>}
  </section>
}
