import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, BarChart3, BookOpen, Check, ChevronRight, Copy, GraduationCap, LoaderCircle, Plus, Pencil, RefreshCw, Trash2, UsersRound } from 'lucide-react'
import { courseErrorMessage, createClassroomSession, deleteClassroomSession, listClassroomSessions, listClassrooms } from '../services/course.service'
import SessionWorkspace from './SessionWorkspace'
import ClassroomRoster from './ClassroomRoster'
import ClassroomEditDialog from './ClassroomEditDialog'
import ClassroomAnnouncements from './ClassroomAnnouncements'
import MaterialRemoveDialog from './documents/MaterialRemoveDialog'
import StudentClassroomPeople from './StudentClassroomPeople'
import '../documents.css'
import '../classrooms.css'

export default function ClassroomWorkspace({ course, initialRoom, onBack, onCourse, onMembersChanged, canManage = true, backLabel }) {
  const [room, setRoom] = useState(initialRoom)
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [copiedCode, setCopiedCode] = useState('')
  useEffect(() => {
    if (!copiedCode) return
    const timer = setTimeout(() => setCopiedCode(''), 2000)
    return () => clearTimeout(timer)
  }, [copiedCode])
  const [tab, setTab] = useState('news')
  const [selected, setSelected] = useState(null)
  const [editing, setEditing] = useState(false)
  const [removeTarget, setRemoveTarget] = useState(null)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')
  const [revision, setRevision] = useState(0)
  const creationLock = useRef(false)
  const [creating, setCreating] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    listClassroomSessions(course.id, room.id, controller.signal)
      .then((rows) => { if (!controller.signal.aborted) setSessions(canManage ? rows : rows.filter((row) => !row.is_draft)) })
      .catch((err) => { if (!controller.signal.aborted) setError(courseErrorMessage(err)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [course.id, room.id, revision, canManage])
  async function addSession() {
    if (creationLock.current || loading) return
    creationLock.current = true; setCreating(true); setError('')
    try {
      const item = await createClassroomSession(course.id, room.id, {})
      setSessions((rows) => [...rows, item])
    } catch (err) { setError(courseErrorMessage(err)) }
    finally { creationLock.current = false; setCreating(false) }
  }
  async function deleteSession() {
    if (creationLock.current || !removeTarget) return
    creationLock.current = true; setDeleting(true); setDeleteError('')
    try {
      await deleteClassroomSession(course.id, room.id, removeTarget.id)
      setSessions((rows) => rows.filter((item) => item.id !== removeTarget.id))
      setRemoveTarget(null); setNotice('Đã xóa buổi học.'); setError('')
    } catch (err) { setDeleteError(courseErrorMessage(err)) }
    finally { creationLock.current = false; setDeleting(false) }
  }
  async function refreshRoster() {
    const rooms = await listClassrooms(course.id)
    setRoom((current) => rooms.find((item) => item.id === current.id) ?? current)
    await onMembersChanged?.()
  }
  async function copy() {
    try { await navigator.clipboard.writeText(room.class_code); setCopiedCode(room.class_code); setError('') }
    catch { setError('Không thể sao chép. Bạn có thể chọn mã lớp để sao chép thủ công.') }
  }
  if (tab === 'sessions' && selected) return <SessionWorkspace canManage={canManage} key={selected.id} course={course} room={room} session={selected} onSaved={(updated) => setSessions((rows) => rows.map((row) => row.id === updated.id ? { ...row, ...updated } : row))} onBack={() => { setSelected(null); setLoading(true); setError(''); setRevision((value) => value + 1) }} />
  return <section className="class-workspace" aria-labelledby="class-workspace-title">
    <div className="class-workspace-navigation"><button type="button" className="back-link" onClick={onBack}><ArrowLeft size={19} />{backLabel || (canManage ? 'Danh sách lớp học' : 'Quay lại khóa học')}</button></div>
    <header className="class-hero">
      <div className="class-hero-art" aria-hidden="true"><GraduationCap size={190} strokeWidth={0.7} /></div>
      <button type="button" className="class-course-link" onClick={onCourse}><BookOpen size={16} />Khóa học<ChevronRight size={14} /><span>{course.title}</span></button>
      <div className="class-hero-title"><span>LỚP HỌC CỦA BẠN</span><h1 id="class-workspace-title">{room.name}</h1></div>
      <div className="class-hero-bottom"><div className="class-hero-facts"><span><UsersRound size={17} />{room.enrolled_count ?? '—'} học viên</span>{canManage && <><span className="class-hero-dot" /> <span>{room.is_join_enabled ? 'Đang mở đăng ký' : 'Đã đóng đăng ký'}</span></>}</div>
        <div className="class-hero-actions">{canManage && <><div className="class-hero-code"><span>Mã lớp</span><code>{room.class_code}</code><button type="button" className="icon-button" onClick={copy} aria-label="Sao chép mã lớp">{copiedCode === room.class_code ? <Check size={17} /> : <Copy size={17} />}</button></div><button type="button" className="class-hero-primary" onClick={() => setEditing(true)}><Pencil size={18} />Chỉnh sửa lớp học</button></>}</div>
      </div>
    </header>
    {error && <div className="error-banner" role="alert">{error}</div>}{notice && <div className="success-banner" role="status"><Check size={18} />{notice}</div>}
    <nav className="detail-tabs class-workspace-tabs" aria-label="Điều hướng lớp học">{[['news', 'Bảng tin'], ['sessions', 'Buổi học'], ['people', 'Học viên'], ['results', 'Kết quả']].map(([value, label]) => <button type="button" key={value} className={tab === value ? 'active' : ''} onClick={() => { setTab(value); setSelected(null) }} aria-current={tab === value ? 'page' : undefined}>{label}</button>)}</nav>
    {tab === 'sessions' && <section className="class-session-list" aria-label="Buổi học">
      <div className="class-content-toolbar">{canManage && <button type="button" className="solid-button" disabled={loading || creating} onClick={addSession}>{creating ? <LoaderCircle size={18} className="spin" /> : <Plus size={18} />}{creating ? 'Đang tạo...' : 'Thêm mới'}</button>}<button type="button" className="icon-button" aria-label="Tải lại buổi học" disabled={loading || creating} onClick={() => { setLoading(true); setError(''); setRevision((value) => value + 1) }}><RefreshCw size={18} /></button></div>
      {loading ? <p className="class-loading"><LoaderCircle className="spin" size={20} />Đang tải buổi học...</p> : sessions.length ? <div className="class-session-rows">{sessions.map((session, index) => <article className="class-session-item" key={session.id}><button type="button" className="class-session-row" onClick={() => setSelected(session)}><span className={`class-session-icon tone-${index % 3}`}><BookOpen size={25} /></span><span className="class-session-summary"><strong>{session.title || 'Buổi học chưa đặt tên'}{session.is_draft && <em className="class-session-draft-tag"> · Bản nháp</em>}</strong><span>Buổi {String(index + 1).padStart(2, '0')}<span>·</span>{session.material_count} học liệu</span></span><ChevronRight size={20} /></button>{canManage && <button type="button" className="class-session-delete" aria-label={`Xóa buổi học ${session.title || 'Buổi học chưa đặt tên'}`} title="Xóa buổi học" disabled={creating || deleting} onClick={() => {setRemoveTarget(session);setDeleteError('')}}><Trash2 size={20} /></button>}</article>)}</div> : !error && <div className="class-session-empty"><span><BookOpen size={34} /></span><h3>Buổi học đầu tiên bắt đầu từ đây</h3><p>Các buổi học và học liệu của lớp sẽ hiển thị tại đây.</p></div>}
    </section>}
    {tab === 'news' && <ClassroomAnnouncements courseId={course.id} roomId={room.id} canManage={canManage} />}
    {tab === 'results' && <section className="class-session-empty class-tab-placeholder" aria-labelledby="class-results-title"><span><BarChart3 size={32} /></span><h2 id="class-results-title">Kết quả học tập</h2><p>Kết quả các bài làm trong buổi học sẽ hiển thị tại đây. Chức năng sẽ được triển khai sau.</p></section>}
    {tab === 'people' && !canManage && <StudentClassroomPeople key={room.id} courseId={course.id} roomId={room.id} />}
    {tab === 'people' && canManage && <ClassroomRoster course={course} room={room} onBack={() => setTab('sessions')} onMembersChanged={refreshRoster} />}
    {removeTarget && <MaterialRemoveDialog title={removeTarget.title || 'Buổi học chưa đặt tên'} headingText="Xóa buổi học?" descriptionText={<>Bạn muốn xóa buổi học <strong>{removeTarget.title || 'Buổi học chưa đặt tên'}</strong>? Buổi học và học liệu bên trong sẽ không còn hiển thị hoặc truy cập được.</>} confirmText="Xác nhận xóa" pendingText="Đang xóa…" pending={deleting} error={deleteError} onCancel={() => {if (!creationLock.current) setRemoveTarget(null)}} onConfirm={deleteSession} />}
    {editing && <ClassroomEditDialog courseId={course.id} room={room} onDeleted={() => { setEditing(false); onBack() }} onClose={() => setEditing(false)} onSaved={(updated) => { setRoom(updated); setEditing(false); setNotice('Đã cập nhật lớp học.') }} />}

  </section>
}

