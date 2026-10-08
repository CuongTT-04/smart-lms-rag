import { useCallback, useEffect, useRef, useState } from 'react'
import CustomSelect from './CustomSelect'
import {
  ArrowLeft, ArrowRight, Check, ChevronDown, CircleCheck, Clock3, DoorOpen,
  GraduationCap, History, LoaderCircle, MessageSquare, RefreshCw, Search, X,
} from 'lucide-react'
import {
  cancelJoinRequest, courseErrorMessage, joinClassroom,
  listMyEnrollments, listMyJoinRequests,
} from '../services/course.service'

const REQUEST_STATES = { PENDING: 'Chờ duyệt', APPROVED: 'Đã chấp nhận', REJECTED: 'Đã từ chối', CANCELED: 'Đã hủy' }
const ENROLLMENT_STATES = { ACTIVE: 'Đang học', COMPLETED: 'Đã hoàn thành', WITHDRAWN: 'Đã thu hồi' }
const TABS = [
  { id: 'pending', label: 'Chờ duyệt', icon: Clock3 },
  { id: 'enrollments', label: 'Lớp đã tham gia', icon: GraduationCap },
  { id: 'history', label: 'Lịch sử yêu cầu', icon: History },
]
const PAGE_SIZE = 5
const validCode = (code) => /^[0-9A-F]{12}$/.test(code)
const date = (value) => new Date(value).toLocaleString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })

export default function StudentEnrollmentPanel({ onCoursesChanged, onOpenCourse }) {
  const [data, setData] = useState(null)
  const [code, setCode] = useState('')
  const [message, setMessage] = useState('')
  const [codeError, setCodeError] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState('')
  const [tab, setTab] = useState('pending')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('')
  const [page, setPage] = useState(1)
  const [cancelTarget, setCancelTarget] = useState(null)
  const busyRef = useRef(false)
  const tabRefs = useRef([])
  const load = useCallback(async (signal) => {
    const [requests, enrollments] = await Promise.all([listMyJoinRequests(signal), listMyEnrollments(signal)])
    return { requests, enrollments }
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    load(controller.signal).then((result) => {
      if (controller.signal.aborted) return
      setData(result)
      if (!result.requests.some((item) => item.status === 'PENDING') && result.enrollments.length) setTab('enrollments')
    }).catch((err) => { if (!controller.signal.aborted) setError(courseErrorMessage(err)) })
    return () => controller.abort()
  }, [load])

  function selectTab(id) {
    setTab(id); setSearch(''); setFilter(''); setPage(1); setCancelTarget(null)
  }
  async function act(key, action) {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(key); setError(''); setNotice(''); setCodeError('')
    try {
      if (action) await action()
      try {
        setData(await load())
        await onCoursesChanged?.()
        if (!action) setNotice('Đã cập nhật danh sách.')
      } catch (err) {
        setError(action ? 'Thao tác đã thành công nhưng chưa tải lại được dữ liệu. Vui lòng làm mới.' : courseErrorMessage(err))
      }
    } catch (err) {
      if (key === 'join' && err.data?.class_code) setCodeError(courseErrorMessage(err))
      else setError(courseErrorMessage(err))
    } finally { setBusy(''); busyRef.current = false }
  }
  function submit(event) {
    event.preventDefault()
    if (!validCode(code)) { setCodeError('Mã lớp phải có 12 ký tự, chỉ gồm số 0–9 và chữ A–F.'); return }
    act('join', async () => {
      const result = await joinClassroom({ class_code: code, message })
      setNotice(result.status === 'ENROLLED' ? 'Bạn đã tham gia lớp học thành công.' : 'Yêu cầu đã được gửi, đang chờ giáo viên xét duyệt.')
      selectTab(result.status === 'ENROLLED' ? 'enrollments' : 'pending')
      setCode(''); setMessage('')
    })
  }

  const pending = (data?.requests || []).filter((item) => item.status === 'PENDING')
  const counts = { pending: pending.length, enrollments: data?.enrollments.length || 0, history: data?.requests.length || 0 }
  const records = tab === 'pending' ? pending : tab === 'enrollments' ? data?.enrollments || [] : data?.requests || []
  const term = search.trim().toLocaleLowerCase('vi')
  const filtered = records.filter((item) => (!filter || item.status === filter) && `${item.classroom_name} ${item.course_title}`.toLocaleLowerCase('vi').includes(term))
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, totalPages)
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
  const states = tab === 'enrollments' ? ENROLLMENT_STATES : REQUEST_STATES

  return <section className="join-workspace" aria-labelledby="join-class-title">
    <header className="join-heading"><div className="join-title"><DoorOpen size={25} aria-hidden="true" /><h1 id="join-class-title">Tham gia lớp học</h1></div><button type="button" className="outline-button join-refresh" disabled={!!busy} onClick={() => act('refresh')} aria-label="Làm mới yêu cầu của tôi">{busy === 'refresh' ? <LoaderCircle className="spin" size={17} /> : <RefreshCw size={17} />} Làm mới</button></header>
    <form className="join-entry" onSubmit={submit}>
      <div className="join-code-row"><label htmlFor="join-class-code">Mã lớp học</label><div className="join-code-actions"><input id="join-class-code" value={code} maxLength={64} autoComplete="off" autoCapitalize="characters" spellCheck={false} placeholder="A1B2C3D4E5F6" aria-invalid={!!codeError} aria-describedby={codeError ? 'join-code-error' : undefined} disabled={!!busy} onChange={(e) => { setCode(e.target.value.replace(/\s/g, '').toUpperCase()); setCodeError('') }} onBlur={() => { if (code && !validCode(code)) setCodeError('Mã lớp phải có 12 ký tự, chỉ gồm số 0–9 và chữ A–F.') }} /><button className="solid-button join-submit" disabled={!!busy || !validCode(code)}>{busy === 'join' ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />} Tham gia lớp</button></div>{codeError && <p id="join-code-error" className="join-field-error" role="alert">{codeError}</p>}</div>
      <details className="join-message"><summary><MessageSquare size={16} /> Lời nhắn cho giáo viên (Tùy chọn) <ChevronDown size={16} /></summary><label className="sr-only" htmlFor="join-message">Lời nhắn cho giáo viên</label><textarea id="join-message" rows={3} maxLength={2000} disabled={!!busy} value={message} onChange={(e) => setMessage(e.target.value)} /><span className="join-character-count">{message.length}/2000</span></details>
    </form>
    {error && <div className="error-banner join-feedback" role="alert">{error}</div>}
    {notice && <div className="success-banner join-feedback" role="status"><Check size={18} />{notice}</div>}
    <div className="join-tabs" role="tablist" aria-label="Theo dõi tham gia lớp">{TABS.map(({ id, label, icon: Icon }, index) => <button key={id} ref={(node) => { tabRefs.current[index] = node }} id={`join-tab-${id}`} type="button" role="tab" aria-selected={tab === id} aria-controls="join-tab-panel" tabIndex={tab === id ? 0 : -1} onClick={() => selectTab(id)} onKeyDown={(event) => {
      const target = event.key === 'ArrowRight' ? (index + 1) % TABS.length : event.key === 'ArrowLeft' ? (index + TABS.length - 1) % TABS.length : event.key === 'Home' ? 0 : event.key === 'End' ? TABS.length - 1 : null
      if (target === null) return
      event.preventDefault(); selectTab(TABS[target].id); tabRefs.current[target]?.focus()
    }}><Icon size={18} aria-hidden="true" /><span>{label}</span><span className="join-count">{data ? counts[id] : '…'}</span></button>)}</div>
    <section id="join-tab-panel" className="join-list-panel" role="tabpanel" aria-labelledby={`join-tab-${tab}`} aria-busy={!data || !!busy}>
      <div className="join-list-toolbar"><label className="join-search"><Search size={18} aria-hidden="true" /><span className="sr-only">Tìm lớp hoặc khóa học</span><input type="search" placeholder="Tìm lớp hoặc khóa học..." value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} /></label>{tab !== 'pending' && <label className="join-status-filter"><span className="sr-only">Lọc trạng thái</span><CustomSelect aria-label="Lọc trạng thái" value={filter} onChange={(e) => { setFilter(e.target.value); setPage(1) }}><option value="">Tất cả trạng thái</option>{Object.entries(states).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</CustomSelect></label>}<span className="join-result-count">{data && `${filtered.length} ${tab === 'enrollments' ? 'lớp' : 'yêu cầu'}`}</span></div>
      {!data ? <div className="join-empty">{error ? <History size={28} /> : <LoaderCircle size={28} className="spin" />}<h2>{error ? 'Chưa tải được dữ liệu' : 'Đang tải danh sách...'}</h2></div> : visible.length ? <div className="join-record-list">{visible.map((item) => <article className="join-record" key={item.id}>
        <span className={`join-record-icon ${tab === 'enrollments' ? 'is-enrolled' : ''}`} aria-hidden="true">{tab === 'enrollments' ? <GraduationCap size={21} /> : item.status === 'PENDING' ? <Clock3 size={21} /> : <History size={21} />}</span>
        <div className="join-record-main"><h2>{item.classroom_name}</h2><p className="join-course-title">{item.course_title}</p><time dateTime={tab === 'enrollments' ? item.enrolled_at : item.created_at}>{date(tab === 'enrollments' ? item.enrolled_at : item.created_at)}</time>
          {item.review_note && <p className="join-review-note"><MessageSquare size={15} aria-hidden="true" /><span>{item.review_note}</span></p>}
          {item.message && tab !== 'enrollments' && <details className="join-sent-message"><summary>Lời nhắn đã gửi <ChevronDown size={14} /></summary><p>{item.message}</p></details>}
          {cancelTarget === item.id && <div className="join-cancel-confirm" role="group" aria-label="Xác nhận hủy yêu cầu"><p>Hủy yêu cầu vào lớp này?</p><div><button type="button" className="outline-button" disabled={!!busy} onClick={() => setCancelTarget(null)}>Giữ yêu cầu</button><button type="button" className="revoke-button" disabled={!!busy} onClick={() => act(item.id, async () => { await cancelJoinRequest(item.id); setCancelTarget(null); setNotice('Đã hủy yêu cầu tham gia.') })}><X size={16} /> Xác nhận hủy</button></div></div>}
        </div>
        <div className="join-record-side"><span className={`request-state ${tab === 'enrollments' ? 'enrollment' : 'request'}-${item.status.toLowerCase()}`}>{item.status === 'PENDING' ? <Clock3 size={14} /> : ['ACTIVE', 'APPROVED', 'COMPLETED'].includes(item.status) ? <CircleCheck size={14} /> : <X size={14} />}{states[item.status]}</span>{tab === 'enrollments' ? <><span className="join-progress">Tiến độ <strong>{item.progress_percent}%</strong></span>{item.status !== 'WITHDRAWN' && onOpenCourse && <button type="button" className="text-button" onClick={() => onOpenCourse(item.course_id)}>Mở khóa học <ArrowRight size={16} /></button>}</> : item.status === 'PENDING' && cancelTarget !== item.id && <button type="button" className="join-cancel-button" disabled={!!busy} onClick={() => setCancelTarget(item.id)}><X size={15} /> Hủy yêu cầu</button>}</div>
      </article>)}</div> : <div className="join-empty">{tab === 'pending' ? <CircleCheck size={30} /> : <Search size={30} />}<h2>{search || filter ? 'Không tìm thấy lớp phù hợp' : tab === 'pending' ? 'Không có yêu cầu đang chờ' : tab === 'enrollments' ? 'Bạn chưa tham gia lớp nào' : 'Chưa có yêu cầu tham gia'}</h2></div>}
      {data && filtered.length > PAGE_SIZE && <footer className="join-pagination"><span>{(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filtered.length)} / {filtered.length}</span><div><button className="icon-button" type="button" title="Trang trước" aria-label="Trang trước" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}><ArrowLeft size={18} /></button><span>Trang {currentPage}/{totalPages}</span><button className="icon-button" type="button" title="Trang sau" aria-label="Trang sau" disabled={currentPage === totalPages} onClick={() => setPage(currentPage + 1)}><ArrowRight size={18} /></button></div></footer>}
    </section>
  </section>
}
