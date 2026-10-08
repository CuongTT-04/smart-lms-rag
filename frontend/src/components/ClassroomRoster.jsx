import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowLeft, Check, LoaderCircle, RefreshCw, Search, UserMinus, UsersRound, X } from 'lucide-react'
import { courseErrorMessage, listClassroomEnrollments, revokeClassroomEnrollment } from '../services/course.service'
import UserAvatar from './UserAvatar'

const STATES = { ACTIVE: 'Đang học', COMPLETED: 'Đã hoàn thành', WITHDRAWN: 'Đã thu hồi' }

export default function ClassroomRoster({ course, room, onBack, onMembersChanged }) {
  const [status, setStatus] = useState('ACTIVE')
  return <section className="enrollment-panel classroom-roster" aria-label={`Học viên lớp ${room.name}`}>
    <button type="button" className="back-button" onClick={onBack}><ArrowLeft size={18} /> Danh sách lớp học</button>
    <div className="section-heading"><div><h2>{room.name}</h2><span className="roster-course-name">{course.title}</span></div><UsersRound size={24} aria-hidden="true" /></div>
    <div className="filter-tabs roster-tabs" aria-label="Trạng thái ghi danh">{[['ACTIVE', 'Đang học'], ['COMPLETED', 'Đã hoàn thành'], ['WITHDRAWN', 'Đã thu hồi'], ['', 'Tất cả']].map(([value, label]) => <button key={value} type="button" aria-pressed={status === value} className={status === value ? 'active' : ''} onClick={() => setStatus(value)}>{label}</button>)}</div>
    <RosterRecords key={`${room.id}:${status}`} course={course} room={room} status={status} onMembersChanged={onMembersChanged} />
  </section>
}

function RosterRecords({ course, room, status, onMembersChanged }) {
  const [records, setRecords] = useState(null)
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [pending, setPending] = useState(false)
  const [confirm, setConfirm] = useState(null)
  const load = useCallback((signal) => listClassroomEnrollments(course.id, room.id, status, signal), [course.id, room.id, status])
  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal)
      .then((result) => { if (!controller.signal.aborted) setRecords(result) })
      .catch((err) => { if (!controller.signal.aborted) setError(courseErrorMessage(err)) })
    return () => controller.abort()
  }, [load])
  async function refresh() {
    setPending(true); setError('')
    try { setRecords(await load()) } catch (err) { setError(courseErrorMessage(err)) }
    finally { setPending(false) }
  }
  async function withdraw() {
    const target = confirm
    setPending(true); setError(''); setNotice('')
    try {
      await revokeClassroomEnrollment(course.id, room.id, target.id)
      setConfirm(null)
      setRecords((current) => current.flatMap((item) => item.id !== target.id ? [item] : status && status !== 'WITHDRAWN' ? [] : [{ ...item, status: 'WITHDRAWN' }]))
      setNotice(`Đã thu hồi ghi danh của ${target.student.full_name || target.student.username} tại lớp ${room.name}.`)
      try { setRecords(await load()); await onMembersChanged() }
      catch { setError('Đã thu hồi thành công nhưng chưa tải lại được dữ liệu. Vui lòng làm mới.') }
    } catch (err) { setError(courseErrorMessage(err)); setConfirm(null) }
    finally { setPending(false) }
  }
  const term = search.trim().toLocaleLowerCase('vi')
  const filtered = (records || []).filter(({ student }) => `${student.full_name || ''} ${student.username} ${student.email || ''}`.toLocaleLowerCase('vi').includes(term))
  return <>
    <div className="roster-toolbar"><label className="search-field"><Search size={18} /><span className="sr-only">Tìm học viên trong lớp</span><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Tên, tài khoản hoặc email..." /></label><span>{records === null ? '' : `${filtered.length} học viên`}</span><button type="button" className="icon-button" title="Làm mới học viên" aria-label="Làm mới học viên của lớp" disabled={pending} onClick={refresh}>{pending ? <LoaderCircle className="spin" size={18} /> : <RefreshCw size={18} />}</button></div>
    {error && <div className="error-banner" role="alert">{error}</div>}
    {notice && <div className="success-banner" role="status"><Check size={18} />{notice}</div>}
    {records === null ? <p className="enrollment-empty">{error ? 'Chưa tải được danh sách học viên.' : 'Đang tải học viên...'}</p> : <div className="enrollment-records">
      {filtered.map((item) => <article className="enrollment-row roster-row" key={item.id}>
        <div className="roster-student"><UserAvatar user={item.student} /><div><strong>{item.student.full_name || item.student.username}</strong><small>{item.student.email || item.student.username}</small><small>Tham gia {new Date(item.enrolled_at).toLocaleDateString('vi-VN')}</small></div></div>
        <span className={`request-state enrollment-${item.status.toLowerCase()}`}>{STATES[item.status]}</span>
        <div className="roster-progress"><progress max={100} value={item.progress_percent} aria-label={`Tiến độ của ${item.student.full_name || item.student.username}`} /><span>{item.progress_percent}%</span></div>
        {item.status !== 'WITHDRAWN' && <button type="button" className="revoke-button" disabled={pending} onClick={() => setConfirm(item)} aria-label={`Thu hồi ghi danh của ${item.student.full_name || item.student.username}`}><UserMinus size={16} /> Thu hồi ở lớp</button>}
      </article>)}
      {!filtered.length && <p className="enrollment-empty">{term ? 'Không tìm thấy học viên phù hợp.' : 'Chưa có học viên ở trạng thái này.'}</p>}
    </div>}
    {confirm && <WithdrawConfirmation record={confirm} room={room} pending={pending} onCancel={() => setConfirm(null)} onConfirm={withdraw} />}
  </>
}

function WithdrawConfirmation({ record, room, pending, onCancel, onConfirm }) {
  const dialog = useRef(null)
  useEffect(() => {
    const previous = document.activeElement
    dialog.current.querySelector('button').focus()
    return () => { if (previous?.isConnected) previous.focus() }
  }, [])
  function keyDown(event) {
    if (event.key === 'Escape' && !pending) onCancel()
    if (event.key !== 'Tab') return
    const buttons = [...dialog.current.querySelectorAll('button:not(:disabled)')]
    if (!buttons.length) { event.preventDefault(); return }
    if (event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons.at(-1).focus() }
    else if (!event.shiftKey && document.activeElement === buttons.at(-1)) { event.preventDefault(); buttons[0].focus() }
  }
  return <div className="modal-layer"><section ref={dialog} className="form-modal" role="dialog" aria-modal="true" aria-labelledby="withdraw-title" aria-describedby="withdraw-description" onKeyDown={keyDown}>
    <h2 id="withdraw-title">Thu hồi ghi danh ở lớp?</h2>
    <p id="withdraw-description"><strong>{record.student.full_name || record.student.username}</strong> sẽ bị thu hồi ghi danh tại <strong>{room.name}</strong>. Các lớp khác không bị thu hồi. Nếu đây là lớp cuối cùng còn hiệu lực, quyền vào khóa học cũng bị thu hồi.</p>
    <div className="modal-actions"><button type="button" className="outline-button" disabled={pending} onClick={onCancel}><X size={17} /> Hủy</button><button type="button" className="solid-button" disabled={pending} onClick={onConfirm}>{pending ? <LoaderCircle className="spin" size={17} /> : <UserMinus size={17} />} Xác nhận thu hồi</button></div>
  </section></div>
}
