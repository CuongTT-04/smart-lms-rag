import { useRef, useState } from 'react'
import CustomSelect from './CustomSelect'
import { ArrowLeft, ArrowRight, BookOpen, CheckCircle2, DoorOpen, GraduationCap, LoaderCircle, RefreshCw, Search } from 'lucide-react'
import { courseErrorMessage } from '../services/course.service'

const PAGE_SIZE = 6
const isCompleted = (course) => !!course.my_classrooms?.length && course.my_classrooms.every((item) => item.status === 'COMPLETED')
const isActive = (course) => course.my_classrooms?.some((item) => item.status === 'ACTIVE')

export default function StudentCoursesView({ courses, search, setSearch, onOpen, onRefresh, onJoin }) {
  const [filter, setFilter] = useState('all')
  const [sort, setSort] = useState('updated')
  const [page, setPage] = useState(1)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const tabRefs = useRef([])
  const lock = useRef(false)
  const tabs = [
    { id: 'all', label: 'Tất cả', count: courses.length },
    { id: 'active', label: 'Đang học', count: courses.filter(isActive).length },
    { id: 'completed', label: 'Đã hoàn thành', count: courses.filter(isCompleted).length },
  ]
  const term = search.trim().toLocaleLowerCase('vi')
  const filtered = courses.filter((course) => (filter === 'all' || (filter === 'active' ? isActive(course) : isCompleted(course))) &&
    `${course.title} ${course.description || ''} ${(course.my_classrooms || []).map((item) => item.classroom_name).join(' ')}`.toLocaleLowerCase('vi').includes(term))
    .sort((a, b) => sort === 'name' ? a.title.localeCompare(b.title, 'vi') : (Date.parse(b.updated_at) || 0) - (Date.parse(a.updated_at) || 0))
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
  function selectTab(id) { setFilter(id); setPage(1) }
  async function refresh() {
    if (lock.current) return
    lock.current = true; setPending(true); setError('')
    try { await onRefresh() } catch (err) { setError(courseErrorMessage(err)) }
    finally { setPending(false); lock.current = false }
  }
  return <section className="my-courses-workspace" aria-labelledby="student-courses-title">
    <header className="join-heading"><div className="join-title"><BookOpen size={25} aria-hidden="true" /><h1 id="student-courses-title">Khóa học của tôi</h1></div><div className="my-courses-actions"><button className="outline-button join-refresh" type="button" title="Làm mới khóa học" aria-label="Làm mới khóa học" disabled={pending} onClick={refresh}>{pending ? <LoaderCircle size={17} className="spin" /> : <RefreshCw size={17} />} Làm mới</button><button className="solid-button" type="button" onClick={onJoin}><DoorOpen size={18} /> Tham gia lớp</button></div></header>
    {error && <div className="error-banner join-feedback" role="alert">{error}</div>}
    <div className="join-tabs" role="tablist" aria-label="Trạng thái khóa học">{tabs.map(({ id, label, count }, index) => <button type="button" key={id} id={`courses-tab-${id}`} ref={(node) => { tabRefs.current[index] = node }} role="tab" aria-selected={filter === id} aria-controls="courses-list-panel" tabIndex={filter === id ? 0 : -1} onClick={() => selectTab(id)} onKeyDown={(event) => {
      const target = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : null
      if (target === null) return
      event.preventDefault(); selectTab(tabs[target].id); tabRefs.current[target]?.focus()
    }}><span>{label}</span><span className="join-count">{count}</span></button>)}</div>
    <section role="tabpanel" id="courses-list-panel" aria-labelledby={`courses-tab-${filter}`} aria-busy={pending}>
      <div className="join-list-toolbar"><label className="join-search"><Search size={18} aria-hidden="true" /><span className="sr-only">Tìm khóa học</span><input type="search" value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} placeholder="Tìm khóa học hoặc tên lớp..." /></label><label className="join-status-filter"><span className="sr-only">Sắp xếp khóa học</span><CustomSelect aria-label="Sắp xếp khóa học" value={sort} onChange={(event) => { setSort(event.target.value); setPage(1) }}><option value="updated">Cập nhật gần nhất</option><option value="name">Tên A–Z</option></CustomSelect></label><span className="join-result-count">{filtered.length} khóa học</span></div>
      {visible.length ? <div className="my-courses-list">{visible.map((course) => {
        const classrooms = course.my_classrooms || []
        return <article className="my-course-row" key={course.id}>
          <span className="my-course-symbol" aria-hidden="true"><BookOpen size={23} /></span>
          <div className="my-course-main"><h2><button type="button" onClick={() => onOpen(course)}>{course.title}</button></h2>{course.description && <p className="my-course-description">{course.description}</p>}
            {classrooms.length ? <div className="my-course-classes"><ul aria-label={`Lớp của khóa học ${course.title}`}>{classrooms.slice(0, 2).map((item) => <li key={item.id}><GraduationCap size={15} aria-hidden="true" />{item.classroom_name}</li>)}</ul>{classrooms.length > 2 && <details><summary>+{classrooms.length - 2} lớp khác</summary><ul>{classrooms.slice(2).map((item) => <li key={item.id}><GraduationCap size={15} aria-hidden="true" />{item.classroom_name}</li>)}</ul></details>}</div> : <span className="my-course-no-class">Chưa có thông tin lớp</span>}
          </div>
          <div className="my-course-side"><span className={`request-state ${isCompleted(course) ? 'enrollment-completed' : isActive(course) ? 'enrollment-active' : ''}`}>{isCompleted(course) ? <CheckCircle2 size={14} /> : <BookOpen size={14} />}{isCompleted(course) ? 'Đã hoàn thành' : isActive(course) ? 'Đang học' : 'Có quyền truy cập'}</span><button className="outline-button" type="button" onClick={() => onOpen(course)}>Xem khóa học <ArrowRight size={17} /></button><time dateTime={course.updated_at}>{course.updated_at ? `Cập nhật ${new Date(course.updated_at).toLocaleDateString('vi-VN')}` : 'Chưa có ngày cập nhật'}</time></div>
        </article>
      })}</div> : <div className="join-empty"><Search size={30} /><h2>{search ? 'Không tìm thấy khóa học' : filter === 'all' ? 'Chưa có khóa học' : filter === 'active' ? 'Chưa có khóa học đang học' : 'Chưa có khóa học hoàn thành'}</h2>{search || filter !== 'all' ? <button type="button" className="text-button" onClick={() => { setSearch(''); selectTab('all') }}>Xóa bộ lọc</button> : <button className="solid-button" type="button" onClick={onJoin}><DoorOpen size={18} /> Tham gia lớp</button>}</div>}
      {filtered.length > PAGE_SIZE && <footer className="join-pagination"><span>{(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filtered.length)} / {filtered.length}</span><div><button className="icon-button" type="button" title="Trang trước" aria-label="Trang trước" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}><ArrowLeft size={18} /></button><span>Trang {currentPage}/{totalPages}</span><button className="icon-button" type="button" title="Trang sau" aria-label="Trang sau" disabled={currentPage === totalPages} onClick={() => setPage(currentPage + 1)}><ArrowRight size={18} /></button></div></footer>}
    </section>
  </section>
}
