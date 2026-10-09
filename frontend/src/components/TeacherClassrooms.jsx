import { useEffect, useMemo, useState } from 'react'
import { BookOpen, ChevronRight, GraduationCap, LoaderCircle, RefreshCw, Search, UsersRound } from 'lucide-react'
import CustomSelect from './CustomSelect'
import { listClassrooms } from '../services/course.service'
import '../classrooms.css'

const searchable = (value) => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').toLowerCase()

export default function TeacherClassrooms({ courses, onOpen }) {
  const [rooms, setRooms] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('ALL')
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    Promise.allSettled(courses.map(async (course) => ({ course, rooms: await listClassrooms(course.id, controller.signal) }))).then((results) => {
      if (controller.signal.aborted) return
      setRooms(results.flatMap((result) => result.status === 'fulfilled' ? result.value.rooms.map((room) => ({ room, course: result.value.course })) : []))
      setError(results.some((result) => result.status === 'rejected') ? 'Chưa tải được lớp của một số khóa học. Vui lòng thử tải lại.' : '')
      setLoading(false)
    })
    return () => controller.abort()
  }, [courses, revision])
  const visible = useMemo(() => rooms.filter(({ room, course }) => (filter === 'ALL' || course.id === filter) && searchable(`${room.name} ${course.title} ${room.class_code}`).includes(searchable(search.trim()))), [rooms, filter, search])
  return <section className="class-directory" aria-labelledby="class-directory-title">
    <div className="page-title"><div><span className="welcome-note"><GraduationCap size={18} /> KHÔNG GIAN LỚP HỌC</span><h1 id="class-directory-title">Lớp học của tôi</h1><p>Mở lớp, chuẩn bị học liệu và đồng hành cùng học viên.</p></div></div>
    <div className="class-directory-toolbar">
      <label className="search-field"><Search size={19} /><span className="sr-only">Tìm lớp học</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tìm tên lớp, khóa học hoặc mã lớp..." /></label>
      <CustomSelect aria-label="Lọc theo khóa học" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="ALL">Tất cả khóa học</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</CustomSelect>
      <button className="icon-button" type="button" aria-label="Tải lại danh sách lớp" onClick={() => { setLoading(true); setRevision((current) => current + 1) }} disabled={loading}><RefreshCw size={19} /></button>
    </div>
    {error && <div className="error-banner" role="alert">{error}</div>}
    {loading ? <p className="class-loading"><LoaderCircle className="spin" size={20} /> Đang tải lớp học...</p> : <>
      <p className="class-result-count">{visible.length} lớp học{filter !== 'ALL' || search ? ' phù hợp' : ''}</p>
      <div className="class-directory-grid">{visible.map(({ room, course }) => <button type="button" className="class-directory-card" key={room.id} onClick={() => onOpen(course, room)} aria-label={`Mở lớp ${room.name}`}>
        <span className="class-card-top"><span className="class-card-symbol"><GraduationCap size={25} /></span><span className={`class-join-badge ${room.is_join_enabled ? 'is-open' : ''}`}>{room.is_join_enabled ? 'Mở đăng ký' : 'Đóng đăng ký'}</span></span>
        <span className="class-directory-course"><BookOpen size={15} />{course.title}</span>
        <span className="class-directory-title">{room.name}<ChevronRight size={21} /></span>
        <span className="class-card-footer"><span><UsersRound size={17} />{room.enrolled_count ?? '—'} học viên</span><span className="class-card-code">{room.class_code}</span></span>
      </button>)}</div>
      {!visible.length && <div className="teacher-empty"><GraduationCap size={35} /><h3>{rooms.length ? 'Không tìm thấy lớp phù hợp' : 'Chưa có lớp học'}</h3><p>{rooms.length ? 'Thử đổi từ khóa hoặc bộ lọc khóa học.' : 'Tạo lớp trong khóa học để bắt đầu tổ chức buổi học.'}</p></div>}
    </>}
  </section>
}
