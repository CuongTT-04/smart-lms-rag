import { useState } from 'react'
import CustomSelect from './CustomSelect'
import { ArrowLeft, ArrowRight, GraduationCap, LoaderCircle, RefreshCw, Search } from 'lucide-react'
import { courseErrorMessage, listMyCourseClassrooms } from '../services/course.service'

export default function StudentCourseClassrooms({ course, onUpdated, onUnavailable }) {
  const [classrooms, setClassrooms] = useState(course.my_classrooms || [])
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('')
  const [page, setPage] = useState(1)
  const filtered = classrooms.filter((item) => (!filter || item.status === filter) && item.classroom_name.toLocaleLowerCase('vi').includes(search.trim().toLocaleLowerCase('vi')))
  const totalPages = Math.max(1, Math.ceil(filtered.length / 5))
  const currentPage = Math.min(page, totalPages)
  const visible = filtered.slice((currentPage - 1) * 5, currentPage * 5)
  async function refresh() {
    setPending(true); setError('')
    try {
      const data = await listMyCourseClassrooms(course.id)
      setClassrooms(data)
      onUpdated?.(data)
    } catch (err) {
      setError(courseErrorMessage(err))
      if (err.status === 403 || err.status === 404) onUnavailable?.(err)
    } finally { setPending(false) }
  }
  return <section className="student-classrooms course-classroom-workspace" aria-labelledby="my-course-classes-title" aria-busy={pending}>
    <div className="section-heading"><div className="course-classes-heading"><h2 id="my-course-classes-title">Lớp học của tôi</h2><span className="join-count">{classrooms.length}</span></div><button className="icon-button" type="button" title="Làm mới lớp học" aria-label="Làm mới lớp học của tôi" disabled={pending} onClick={refresh}>{pending ? <LoaderCircle size={18} className="spin" /> : <RefreshCw size={18} />}</button></div>
    {error && <div className="error-banner" role="alert">{error}</div>}
    {classrooms.length > 5 && <div className="join-list-toolbar"><label className="join-search"><Search size={18} /><span className="sr-only">Tìm lớp trong khóa học</span><input type="search" placeholder="Tìm tên lớp..." value={search} onChange={(event) => { setSearch(event.target.value); setPage(1) }} /></label><label className="join-status-filter"><span className="sr-only">Lọc lớp theo trạng thái</span><CustomSelect aria-label="Lọc lớp theo trạng thái" value={filter} onChange={(event) => { setFilter(event.target.value); setPage(1) }}><option value="">Tất cả trạng thái</option><option value="ACTIVE">Đang học</option><option value="COMPLETED">Đã hoàn thành</option></CustomSelect></label></div>}
    <div className="course-classroom-list">{visible.map((item) => <article className="join-record course-classroom-row" key={item.id}>
      <span className="join-record-icon is-enrolled"><GraduationCap size={21} aria-hidden="true" /></span><div className="join-record-main"><h3>{item.classroom_name}</h3><p className="course-class-dates">Tham gia <time dateTime={item.enrolled_at}>{new Date(item.enrolled_at).toLocaleDateString('vi-VN')}</time>{item.completed_at && <span>Hoàn thành <time dateTime={item.completed_at}>{new Date(item.completed_at).toLocaleDateString('vi-VN')}</time></span>}</p></div>
      <span className={`request-state enrollment-${item.status.toLowerCase()}`}>{item.status === 'COMPLETED' ? 'Đã hoàn thành' : 'Đang học'}</span>
      <div className="course-class-progress"><span>Tiến độ <strong>{item.progress_percent}%</strong></span><progress value={item.progress_percent} max={100} aria-label={`Tiến độ lớp ${item.classroom_name}`} /></div>
    </article>)}{!visible.length && <div className="join-empty"><GraduationCap size={30} /><h3>{classrooms.length ? 'Không tìm thấy lớp phù hợp' : 'Chưa có thông tin lớp đang tham gia.'}</h3></div>}</div>
    {filtered.length > 5 && <footer className="join-pagination"><span>{(currentPage - 1) * 5 + 1}–{Math.min(currentPage * 5, filtered.length)} / {filtered.length}</span><div><button type="button" className="icon-button" title="Trang lớp trước" aria-label="Trang lớp trước" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}><ArrowLeft size={18} /></button><span>Trang {currentPage}/{totalPages}</span><button type="button" className="icon-button" title="Trang lớp sau" aria-label="Trang lớp sau" disabled={currentPage === totalPages} onClick={() => setPage(currentPage + 1)}><ArrowRight size={18} /></button></div></footer>}
  </section>
}
