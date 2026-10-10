import { useCallback, useEffect, useState } from 'react'
import CustomSelect from './CustomSelect'
import { Check, Copy, LoaderCircle, Pencil, Plus, RefreshCw, UsersRound, X } from 'lucide-react'
import ClassroomRoster from './ClassroomRoster'
import ClassroomEditDialog from './ClassroomEditDialog'
import {
  courseErrorMessage, createClassroom,
  listClassrooms, listJoinRequests, reviewJoinRequest,
} from '../services/course.service'

const REQUEST_STATUS = { PENDING: 'Chờ duyệt', APPROVED: 'Đã chấp nhận', REJECTED: 'Đã từ chối', CANCELED: 'Đã hủy' }
const date = (value) => new Date(value).toLocaleString('vi-VN')

function Feedback({ error, notice }) {
  return <>{error && <div className="error-banner" role="alert">{error}</div>}{notice && <div className="success-banner" role="status"><Check size={18} />{notice}</div>}</>
}

export function TeacherEnrollmentPanel({ course, onMembersChanged, onOpenClassroom, requestsOnly = false }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [copiedCode, setCopiedCode] = useState('')
  useEffect(() => {
    if (!copiedCode) return
    const timer = setTimeout(() => setCopiedCode(''), 2000)
    return () => clearTimeout(timer)
  }, [copiedCode])
  const [busy, setBusy] = useState('')
  const [name, setName] = useState('')
  const [filter, setFilter] = useState('PENDING')
  const [review, setReview] = useState(null)
  const [note, setNote] = useState('')
  const [selectedRoom, setSelectedRoom] = useState(null)
  const [editingRoom, setEditingRoom] = useState(null)
  const load = useCallback(async (signal) => {
    const [classrooms, requests] = await Promise.all([
      listClassrooms(course.id, signal), listJoinRequests(course.id, '', signal),
    ])
    return { classrooms, requests }
  }, [course.id])
  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
      .then((result) => { if (!controller.signal.aborted) setData(result) })
      .catch((err) => { if (!controller.signal.aborted) setError(courseErrorMessage(err)) })
    return () => controller.abort()
  }, [load])

  async function act(key, action, message) {
    setBusy(key); setError(''); setNotice('')
    try {
      await action()
      setNotice(message)
      try { setData(await load()); await onMembersChanged() }
      catch { setError('Thao tác đã thành công nhưng chưa tải lại được dữ liệu. Vui lòng làm mới.') }
    } catch (err) { setError(courseErrorMessage(err)) }
    finally { setBusy('') }
  }
  async function copy(code) {
    try { await navigator.clipboard.writeText(code); setCopiedCode(code); setError('') }
    catch { setError('Không thể sao chép tự động. Bạn có thể chọn và sao chép mã lớp.') }
  }

  if (selectedRoom && !requestsOnly) return <ClassroomRoster course={course} room={selectedRoom} onBack={() => setSelectedRoom(null)} onMembersChanged={onMembersChanged} />

  return <section className="enrollment-panel" aria-label={requestsOnly ? 'Yêu cầu tham gia' : 'Quản lý lớp học'}>
    <div className="section-heading"><h2>{requestsOnly ? 'Yêu cầu tham gia' : 'Lớp học và quyền tham gia'}</h2><button type="button" className="icon-button" title="Làm mới" aria-label="Làm mới lớp và yêu cầu" disabled={!!busy} onClick={() => act('refresh', async () => {}, 'Đã làm mới dữ liệu.')}><RefreshCw size={18} /></button></div>
    <Feedback error={error} notice={notice} />
    {!data ? <p>{error ? 'Chưa tải được dữ liệu.' : 'Đang tải dữ liệu...'}</p> : requestsOnly ? <>
      <label className="enrollment-filter">Trạng thái yêu cầu<CustomSelect aria-label="Trạng thái yêu cầu" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="">Tất cả</option>{Object.entries(REQUEST_STATUS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</CustomSelect></label>
      <div className="enrollment-records">{data.requests.filter((item) => !filter || item.status === filter).map((item) => <article className="enrollment-row" key={item.id}>
        <div><strong>{item.student.full_name || item.student.username}</strong><small>{item.student.email} · {item.classroom_name}</small><small>{date(item.created_at)}</small>{item.message && <p>{item.message}</p>}{item.review_note && <p>Phản hồi: {item.review_note}</p>}</div>
        <span className={`request-state request-${item.status.toLowerCase()}`}>{REQUEST_STATUS[item.status]}</span>
        {item.status === 'PENDING' && <div className="enrollment-actions"><button className="outline-button" disabled={!!busy} onClick={() => { setReview({ item, decision: 'reject' }); setNote('') }}><X size={16} /> Từ chối</button><button className="solid-button" disabled={!!busy} onClick={() => { setReview({ item, decision: 'approve' }); setNote('') }}><Check size={16} /> Chấp nhận</button></div>}
      </article>)}{!data.requests.some((item) => !filter || item.status === filter) && <p className="enrollment-empty">Không có yêu cầu ở trạng thái này.</p>}</div>
      {review && <form className="enrollment-review" onSubmit={(e) => { e.preventDefault(); const current = review; act('review', async () => { await reviewJoinRequest(course.id, current.item.id, { decision: current.decision, review_note: note }); setReview(null) }, current.decision === 'approve' ? 'Đã chấp nhận học viên vào lớp.' : 'Đã từ chối yêu cầu.') }}>
        <h3>{review.decision === 'approve' ? 'Chấp nhận' : 'Từ chối'}: {review.item.student.full_name || review.item.student.username}</h3>
        <label>Ghi chú phản hồi<textarea maxLength={2000} rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></label>
        <div className="enrollment-actions"><button type="button" className="outline-button" disabled={!!busy} onClick={() => setReview(null)}>Hủy</button><button className="solid-button" disabled={!!busy}>{busy ? <LoaderCircle size={17} className="spin" /> : <Check size={17} />} Xác nhận</button></div>
      </form>}
    </> : <>
      {course.status !== 'PUBLISHED' && <p className="enrollment-warning">Khóa học chưa xuất bản, học viên chưa thể tham gia.</p>}
      <form className="enrollment-create" onSubmit={(e) => { e.preventDefault(); act('create', async () => { await createClassroom(course.id, { name: name.trim() }); setName('') }, 'Đã tạo lớp học mới.') }}>
        <label>Tên lớp mới<input required maxLength={255} value={name} onChange={(e) => setName(e.target.value)} /></label><button className="solid-button" disabled={!!busy || !name.trim()}><Plus size={17} /> Tạo lớp</button>
      </form>
      <div className="enrollment-records">{data.classrooms.map((room) => <ClassroomRow key={room.id} room={room} busy={!!busy} copied={copiedCode === room.class_code} onCopy={copy} onRoster={() => setSelectedRoom(room)} onEdit={() => setEditingRoom(room)} onOpen={onOpenClassroom ? () => onOpenClassroom(room) : undefined} />)}</div>
    </>}
    {editingRoom && <ClassroomEditDialog courseId={course.id} room={editingRoom} onDeleted={(id) => { setData((current) => ({ ...current, classrooms: current.classrooms.filter((item) => item.id !== id), requests: current.requests.filter((item) => item.classroom_id !== id) })); setEditingRoom(null); setNotice('Đã xóa lớp học.'); onMembersChanged?.() }} onClose={() => setEditingRoom(null)} onSaved={(room) => { setData((current) => ({ ...current, classrooms: current.classrooms.map((item) => item.id === room.id ? room : item) })); setNotice('Đã cập nhật lớp học.'); setError(''); setEditingRoom(null) }} />}
  </section>
}

function ClassroomRow({ room, busy, copied, onCopy, onEdit, onRoster, onOpen }) {
  return <article className={`enrollment-row classroom-row ${onOpen ? 'is-clickable' : ''}`}>
    <div className="classroom-name-field"><span>Tên lớp</span><div className="classroom-name-value">{onOpen ? <button type="button" className="classroom-name-link" onClick={onOpen} aria-label={`Mở lớp ${room.name}`}>{room.name}</button> : room.name}</div></div>
    <div className="class-code"><code>{room.class_code}</code><button type="button" className="icon-button" title="Sao chép mã lớp" aria-label={`Sao chép mã ${room.class_code}`} onClick={() => onCopy(room.class_code)}>{copied ? <Check size={17} /> : <Copy size={17} />}</button></div>
    <button type="button" className="outline-button" disabled={busy} onClick={onEdit} aria-label={`Chỉnh sửa lớp ${room.name}`}><Pencil size={16} /> Chỉnh sửa</button>
    <button type="button" className="outline-button" disabled={busy} onClick={onRoster} aria-label={`Học viên lớp ${room.name}`}><UsersRound size={16} /> Học viên</button>
  </article>
}

export { default as StudentEnrollmentPanel } from './StudentEnrollmentPanel'
