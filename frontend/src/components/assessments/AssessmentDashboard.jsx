import { useEffect, useRef, useState } from 'react'
import { Download, RefreshCw, Search, ShieldAlert, Users } from 'lucide-react'
import VideoDialog from '../videos/VideoDialog'
import { assessmentWrite, downloadAssessmentFile, getAssessment } from '../../services/assessment.service'
import { courseErrorMessage } from '../../services/course.service'
import { dateLabel, correctIds, answerIds } from './assessmentUtils'
import { useHistoryState } from '../../hooks/useHistoryState'

const statusText = { NOT_SUBMITTED: 'Chưa nộp', PENDING: 'Chờ chấm', GRADED: 'Đã chấm' }
function Bars({ title, rows, suffix = '' }) {
  const max = Math.max(1, ...rows.map((r) => r.value))
  return <section className="assessment-chart" aria-label={title}><h3>{title}</h3>{!rows.length || rows.every((r) => !r.value) ? <p className="assessment-muted">Chưa có dữ liệu.</p> : <div className="assessment-bars">{rows.map((r, i) => <div className="assessment-bar-row" key={i}><span title={r.label}>{r.label}</span><div><i style={{ width: `${Math.max(1, r.value/max*100)}%` }} /></div><strong>{r.value}{suffix}</strong></div>)}</div>}</section>
}
function GradeDialog({ path, initial, onClose, onSaved }) {
  const [info, setInfo] = useState(initial)
  const [score, setScore] = useState(initial.score ?? '')
  const [feedback, setFeedback] = useState(initial.feedback || '')
  const [published, setPublished] = useState(initial.grade_published)
  const [moderation, setModeration] = useState(initial.moderation_note || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const filePath = `${path}attempts/${info.id}/`
  return <VideoDialog title={`${info.student_name} · Lượt ${info.number}`} pending={busy} onClose={onClose}><div className="assessment-review">
    {error && <p className="error-banner" role="alert">{error}</p>}
    <p>Nộp lúc {dateLabel(info.submitted_at)}{info.auto_submitted ? ' · Tự chốt khi hết giờ' : ''}</p>
    {info.questions?.length ? info.questions.map((q, index) => <article key={q.id} className="assessment-review-question"><strong>Câu {index+1}: {q.prompt}</strong>{q.choices.map((c) => <p key={c.id} className={correctIds(q).includes(c.id) ? 'assessment-correct' : ''}>{answerIds(info.answers[q.id]).includes(c.id) ? q.multiple ? '☑ ' : '● ' : q.multiple ? '☐ ' : '○ '}{c.text}{correctIds(q).includes(c.id) ? ' · Đáp án đúng' : ''}</p>)}</article>) : <p className="assessment-prewrap">{info.text || 'Bài nộp bằng tệp.'}</p>}
    {info.file_name && <button className="outline-button" type="button" onClick={() => downloadAssessmentFile(`${filePath}file/`, info.file_name).catch((err) => setError(courseErrorMessage(err)))}><Download size={16} />{info.file_name}</button>}
    {info.events?.length > 0 && <details className="assessment-event-list"><summary><ShieldAlert size={16} />{info.events.length} sự kiện cần xem xét</summary><ul>{info.events.map((e) => <li key={e.event_id}>{e.kind === 'TAB_HIDDEN' ? 'Chuyển tab/ẩn trang' : 'Thoát toàn màn hình'} · {dateLabel(e.created_at)}</li>)}</ul><p className="assessment-muted">Đây là tín hiệu từ trình duyệt, không phải kết luận gian lận. Giáo viên quyết định cách xử lý.</p></details>}
    {info.status !== 'SUBMITTED' ? <p className="assessment-muted">Học viên chưa nộp. Có thể xem bài đã lưu và log, chưa chấm điểm.</p> : <form className="assessment-form" onSubmit={async (event) => {
      event.preventDefault(); if (busy) return; setBusy(true); setError('')
      try { const updated = await assessmentWrite(`${filePath}grade/`, 'PATCH', { ...(score !== '' ? { score: Number(score) } : {}), feedback, published, moderation_note: moderation }); setInfo(updated); onSaved() }
      catch (err) { setError(courseErrorMessage(err)) } finally { setBusy(false) }
    }}>
      <label>Điểm (0–10)<input type="number" min={0} max={10} step="0.01" value={score} disabled={busy} onChange={(e) => setScore(e.target.value)} /></label>
      <label>Nhận xét cho học viên<textarea rows={3} maxLength={5000} value={feedback} disabled={busy} onChange={(e) => setFeedback(e.target.value)} /></label>
      <label>Ghi nhận xử lý vi phạm (nội bộ)<textarea rows={2} maxLength={5000} value={moderation} disabled={busy} onChange={(e) => setModeration(e.target.value)} /></label>
      <label className="assessment-checkbox"><input type="checkbox" checked={published} disabled={busy} onChange={(e) => setPublished(e.target.checked)} />Công bố kết quả lượt này</label>
      <button type="submit" className="solid-button" disabled={busy}>{busy ? 'Đang lưu...' : 'Lưu điểm và phản hồi'}</button>
    </form>}
    {info.grade_history?.length > 0 && <details><summary>Lịch sử chấm và xử lý ({info.grade_history.length})</summary>{info.grade_history.map((entry, i) => <p key={i}>{dateLabel(entry.created_at)} · {entry.before.score ?? 'Chưa chấm'} → {entry.after.score ?? 'Chưa chấm'} · {entry.after.feedback}{entry.after.moderation_note ? ` · ${entry.after.moderation_note}` : ''}</p>)}</details>}
  </div></VideoDialog>
}
export default function AssessmentDashboard({ path, info }) {
  const [data, setData] = useState(null)
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [revision, setRevision] = useState(0)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [requestedAttempt, setRequestedAttempt] = useHistoryState(`assessment.${info.id}.attempt`, null)
  useEffect(() => {
    if (!requestedAttempt) return
    const controller = new AbortController()
    getAssessment(`${path}attempts/${requestedAttempt}/`, controller.signal)
      .then((attempt) => { if (!controller.signal.aborted) setSelected(attempt) })
      .catch((err) => { if (!controller.signal.aborted) setError(courseErrorMessage(err)) })
    return () => controller.abort()
  }, [path, requestedAttempt])

  const [exporting, setExporting] = useState(false)
  const request = useRef(0)
  const filters = new URLSearchParams({ q, status }).toString()
  useEffect(() => {
    const controller = new AbortController()
    const id = ++request.current
    const timer = setTimeout(() => {
      getAssessment(`${path}dashboard/?${filters}`, controller.signal).then((result) => { if (id === request.current && !controller.signal.aborted) { setData({ ...result, filterKey: filters }); setError('') } }).catch((err) => { if (!controller.signal.aborted) setError(courseErrorMessage(err)) })
    }, 250)
    return () => { clearTimeout(timer); controller.abort() }
  }, [path, filters, revision])
  const current = data?.filterKey === filters ? data : null
  return <section className="assessment-dashboard" aria-label="Dashboard bài tập"><div className="assessment-dashboard-heading"><h3><Users size={20} />Dashboard · {info.mode === 'TEST' ? 'Kiểm tra' : 'Ôn tập'}</h3><div className="assessment-actions"><button className="outline-button" type="button" disabled={!current || exporting} onClick={async () => { setExporting(true); try { await downloadAssessmentFile(`${path}export/?${filters}`, `ket-qua-${info.id}.xlsx`, 'xlsx') } catch (err) { setError(courseErrorMessage(err)) } finally { setExporting(false) } }}><Download size={17} />{exporting ? 'Đang xuất...' : 'Xuất Excel'}</button><button type="button" className="icon-button" aria-label="Làm mới dashboard" onClick={() => setRevision((v) => v+1)}><RefreshCw size={18} /></button></div></div>
    <div className="assessment-filters"><label><Search size={17} /><input aria-label="Tìm học viên" placeholder="Tìm học viên..." value={q} onChange={(e) => setQ(e.target.value)} /></label><select aria-label="Trạng thái bài nộp" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Tất cả trạng thái</option><option value="NOT_SUBMITTED">Chưa nộp</option><option value="PENDING">Chờ chấm</option><option value="GRADED">Đã chấm</option></select></div>
    {error && <p className="error-banner" role="alert">{error}</p>}
    {!current ? <p role="status">Đang tải thống kê...</p> : <><div className="assessment-metrics">{[['Học viên', current.summary.total], ['Đã nộp', current.summary.submitted], ['Chưa nộp', current.summary.not_submitted], ['Chờ chấm', current.summary.pending], ['Điểm trung bình', current.summary.average ?? '—'], ...(info.mode === 'TEST' ? [['Sự kiện vi phạm', current.summary.violations]] : [])].map(([label, value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}</div>
    <p className="assessment-muted">Thống kê điểm dựa trên lượt đã nộp mới nhất của mỗi học viên. Lịch sử mọi lượt vẫn được giữ. Áp dụng bộ lọc hiện tại cho cả biểu đồ và Excel.</p>
    <div className="assessment-charts"><Bars title="Tiến độ nộp bài" rows={[{label:'Đã nộp', value:current.summary.submitted}, {label:'Chưa nộp', value:current.summary.not_submitted}]} /><Bars title="Phân bố điểm" rows={current.score_distribution.map((r) => ({label:r.label, value:r.count}))} /><Bars title="Bài nộp theo ngày" rows={current.submissions_by_day.map((r) => ({label:r.date, value:r.count}))} />{info.kind === 'QUIZ' && <Bars title="Tỷ lệ đúng từng câu" suffix="%" rows={current.question_stats.map((r, i) => ({label:`Câu ${i+1}: ${r.prompt}`, value:r.total ? Math.round(r.correct/r.total*100) : 0}))} />}</div>
    <div className="assessment-table-wrap"><table className="assessment-table"><caption>Tổng hợp học viên</caption><thead><tr><th>Học viên</th><th>Trạng thái</th><th>Số lượt</th><th>Điểm mới nhất</th>{info.mode === 'TEST' && <th>Vi phạm</th>}<th>Bài làm</th></tr></thead><tbody>{current.students.map((r) => <tr key={r.student_id}><td>{r.name}{!r.active && <small> · Đã rời lớp</small>}</td><td>{statusText[r.status]}</td><td>{r.attempt_count}</td><td>{r.latest?.score ?? '—'}</td>{info.mode === 'TEST' && <td>{r.violation_count}</td>}<td>{r.latest ? <button className="outline-button" type="button" onClick={() => setSelected(r.latest)}>Xem / chấm</button> : 'Chưa nộp'}</td></tr>)}</tbody></table>{!current.students.length && <p className="assessment-muted">Không có học viên phù hợp.</p>}</div>
    <details className="assessment-all-attempts"><summary>Lịch sử tất cả lượt làm ({current.attempts.length})</summary>{current.attempts.map((a) => <button key={a.id} type="button" className="assessment-history-row" onClick={() => setSelected(a)}><span>{a.student_name} · Lượt {a.number} · {a.status === 'DRAFT' ? 'Đang làm' : dateLabel(a.submitted_at)}</span><strong>{a.score ?? 'Chưa chấm'}</strong></button>)}</details></>}
    {selected && <GradeDialog key={selected.id} path={path} initial={selected} onClose={() => { setSelected(null); setRequestedAttempt(null) }} onSaved={() => setRevision((v) => v+1)} />}
  </section>
}
