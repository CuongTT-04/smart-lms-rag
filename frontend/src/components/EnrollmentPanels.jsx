import { useCallback, useEffect, useState } from 'react'
import CustomSelect from './CustomSelect'
import { Check, Copy, LoaderCircle, Plus, RefreshCw, UsersRound, X } from 'lucide-react'
import ClassroomRoster from './ClassroomRoster'
import {
  courseErrorMessage, createClassroom, getAccessPolicy,
  listClassrooms, listJoinRequests, reviewJoinRequest, updateAccessPolicy, updateClassroom,
} from '../services/course.service'

const REQUEST_STATUS = { PENDING: 'Chờ duyệt', APPROVED: 'Đã chấp nhận', REJECTED: 'Đã từ chối', CANCELED: 'Đã hủy' }
const date = (value) => new Date(value).toLocaleString('vi-VN')

function Feedback({ error, notice }) {
  return <>{error && <div className="error-banner" role="alert">{error}</div>}{notice && <div className="success-banner" role="status"><Check size={18} />{notice}</div>}</>
}

export function TeacherEnrollmentPanel({ course, onMembersChanged, requestsOnly = false }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')
  const [name, setName] = useState('')
  const [filter, setFilter] = useState('PENDING')
  const [review, setReview] = useState(null)
  const [note, setNote] = useState('')
  const [selectedRoom, setSelectedRoom] = useState(null)
  const load = useCallback(async (signal) => {
    const [policy, classrooms, requests] = await Promise.all([
      getAccessPolicy(course.id, signal), listClassrooms(course.id, signal), listJoinRequests(course.id, '', signal),
    ])
    return { policy, classrooms, requests }
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
    try { await navigator.clipboard.writeText(code); setNotice('Đã sao chép mã lớp.'); setError('') }
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
      <form className="enrollment-policy" onSubmit={(e) => { e.preventDefault(); act('policy', () => updateAccessPolicy(course.id, { require_approval: data.policy.require_approval, visibility: data.policy.visibility }), 'Đã lưu chính sách tham gia.') }}>
        <label className="enrollment-check"><input type="checkbox" checked={data.policy.require_approval} onChange={(e) => setData({ ...data, policy: { ...data.policy, require_approval: e.target.checked } })} /> Yêu cầu giáo viên xét duyệt</label>
        <label>Mức hiển thị<CustomSelect aria-label="Mức hiển thị" value={data.policy.visibility} onChange={(e) => setData({ ...data, policy: { ...data.policy, visibility: e.target.value } })}><option value="PRIVATE">Riêng tư</option><option value="PUBLIC">Công khai</option></CustomSelect></label>
        <button className="solid-button" disabled={!!busy}><Check size={17} /> Lưu chính sách</button>
      </form>
      {course.status !== 'PUBLISHED' && <p className="enrollment-warning">Khóa học chưa xuất bản, học viên chưa thể tham gia.</p>}
      <form className="enrollment-create" onSubmit={(e) => { e.preventDefault(); act('create', async () => { await createClassroom(course.id, { name: name.trim() }); setName('') }, 'Đã tạo lớp học mới.') }}>
        <label>Tên lớp mới<input required maxLength={255} value={name} onChange={(e) => setName(e.target.value)} /></label><button className="solid-button" disabled={!!busy || !name.trim()}><Plus size={17} /> Tạo lớp</button>
      </form>
      <div className="enrollment-records">{data.classrooms.map((room) => <ClassroomRow key={`${room.id}:${room.name}`} room={room} busy={!!busy} onCopy={copy} onRoster={() => setSelectedRoom(room)} onSave={(values) => act(room.id, () => updateClassroom(course.id, room.id, values), 'Đã cập nhật lớp học.')} />)}</div>
    </>}
  </section>
}

function ClassroomRow({ room, busy, onCopy, onSave, onRoster }) {
  const [name, setName] = useState(room.name)
  return <form className="enrollment-row classroom-row" onSubmit={(e) => { e.preventDefault(); onSave({ name: name.trim() }) }}>
    <label>Tên lớp<input aria-label={`Tên lớp ${room.name}`} required maxLength={255} value={name} onChange={(e) => setName(e.target.value)} /></label>
    <div className="class-code"><code>{room.class_code}</code><button type="button" className="icon-button" title="Sao chép mã lớp" aria-label={`Sao chép mã ${room.class_code}`} onClick={() => onCopy(room.class_code)}><Copy size={17} /></button></div>
    <label className="enrollment-check"><input type="checkbox" checked={room.is_join_enabled} disabled={busy} onChange={(e) => onSave({ is_join_enabled: e.target.checked })} /> Mở đăng ký</label>
    <button className="outline-button" disabled={busy || !name.trim() || name.trim() === room.name}><Check size={16} /> Lưu tên</button>
    <button type="button" className="outline-button" disabled={busy} onClick={onRoster} aria-label={`Học viên lớp ${room.name}`}><UsersRound size={16} /> Học viên</button>
  </form>
}

export { default as StudentEnrollmentPanel } from './StudentEnrollmentPanel'
