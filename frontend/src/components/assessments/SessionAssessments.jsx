import { useEffect, useState } from 'react'
import { ClipboardList, Pencil, RefreshCw, Trash2 } from 'lucide-react'
import AssessmentEditor from './AssessmentEditor'
import AssessmentRunner from './AssessmentRunner'
import { dateLabel, correctIds } from './assessmentUtils'
import AssessmentDashboard from './AssessmentDashboard'
import VideoDialog from '../videos/VideoDialog'
import { assessmentWrite, getAssessment } from '../../services/assessment.service'
import { courseErrorMessage } from '../../services/course.service'
import './assessments.css'

export default function SessionAssessments({ path, rows, selectedId, canManage, onSelect, onRefresh, listError, creating, onCreatingChange, onTestActive }) {
  const selected = rows.find((r) => r.id === selectedId) || rows[0]
  const detailPath = selected ? `${path}${selected.id}/` : null
  const [loaded, setLoaded] = useState(null)
  const [revision, setRevision] = useState(0)
  const [editing, setEditing] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [tab, setTab] = useState('dashboard')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const info = loaded?.id === selected?.id ? loaded : null
  useEffect(() => {
    if (!detailPath) return
    const controller = new AbortController()
    getAssessment(detailPath, controller.signal).then((data) => { if (!controller.signal.aborted) { setLoaded(data); setError('') } }).catch((err) => { if (!controller.signal.aborted) setError(courseErrorMessage(err)) })
    return () => controller.abort()
  }, [detailPath, revision])
  async function update(values) {
    if (busy) return
    setBusy(true); setError('')
    try { const data = await assessmentWrite(detailPath, 'PATCH', values); setLoaded(data); await onRefresh() }
    catch (err) { setError(courseErrorMessage(err)) } finally { setBusy(false) }
  }
  return <section className="session-assessments" aria-label="Bài tập buổi học"><div className="assessment-heading"><div><span className="video-eyebrow">BÀI TẬP BUỔI HỌC</span><h2>{info?.title || 'Bài tập và kiểm tra'}</h2></div><div className="assessment-actions"><button type="button" className="icon-button" aria-label="Làm mới bài tập" onClick={() => { setRevision((v) => v+1); onRefresh() }}><RefreshCw size={18} /></button></div></div>
    {(error || listError) && <p className="error-banner" role="alert">{error || listError}</p>}
    {!selected ? <div className="assessment-empty"><ClipboardList size={40} /><h3>{canManage ? 'Tạo hoạt động học tập đầu tiên' : 'Chưa có bài tập được công bố'}</h3><p>{canManage ? 'Quiz hoặc tự luận/nộp file, với chế độ Ôn tập hoặc Kiểm tra.' : 'Bài tập sẽ xuất hiện khi giáo viên công bố.'}</p></div> : !info ? <p role="status">Đang tải bài tập...</p> : <>
      <div className="assessment-meta"><span className={`assessment-badge ${info.mode === 'TEST' ? 'is-test' : ''}`}>{info.mode === 'TEST' ? 'Kiểm tra' : 'Ôn tập'}</span><span>{info.kind === 'QUIZ' ? `Quiz · ${info.questions.length} câu · ${info.duration_seconds/60} phút` : 'Tự luận / nộp file'}</span><span>Hạn: {dateLabel(info.due_at)}</span>{canManage && <span>{info.is_published ? 'Đã công bố' : 'Bản nháp'}</span>}</div>
      {info.description && <p className="assessment-description assessment-prewrap">{info.description}</p>}
      {canManage ? <><div className="assessment-actions"><button className="outline-button" type="button" disabled={busy} onClick={() => update({is_published:!info.is_published})}>{info.is_published ? 'Thu hồi công bố' : 'Công bố bài tập'}</button><button className="outline-button" type="button" disabled={busy || info.locked} title={info.locked ? 'Đã có lượt làm, đề được giữ nguyên. Tạo bài mới để thay đổi.' : 'Chỉnh sửa đề'} onClick={() => setEditing(true)}><Pencil size={16} />Chỉnh sửa</button><button className="outline-button" type="button" disabled={busy} onClick={() => update({results_published:!info.results_published})}>{info.results_published ? 'Ẩn điểm toàn bài' : 'Công bố điểm toàn bài'}</button>{info.kind === 'QUIZ' && <button className="outline-button" type="button" disabled={busy} onClick={() => update({solutions_published:!info.solutions_published})}>{info.solutions_published ? 'Ẩn đáp án' : 'Công bố đáp án'}</button>}<button className="icon-button video-danger" type="button" disabled={busy} aria-label="Gỡ bài tập" onClick={() => setRemoving(true)}><Trash2 size={17} /></button></div>
      {info.mode === 'TEST' && info.solutions_published && <p className="assessment-muted">Đáp án kiểm tra chỉ được mở cho lượt đã nộp sau hạn của bài.</p>}
      <nav className="detail-tabs" aria-label="Quản lý bài tập"><button className={tab === 'dashboard' ? 'active' : ''} type="button" onClick={() => setTab('dashboard')}>Dashboard và chấm bài</button><button className={tab === 'questions' ? 'active' : ''} type="button" onClick={() => setTab('questions')}>Xem đề</button></nav>
      {tab === 'dashboard' ? info.is_published || info.locked ? <AssessmentDashboard key={info.id} path={detailPath} info={info} /> : <p className="assessment-policy">Hoàn thiện và công bố bài tập để mở dashboard. Bạn có thể xem đề trước khi công bố.</p> : <div className="assessment-questions">{info.questions.map((q, i) => <article key={q.id}><h3>Câu {i+1}</h3><p className="assessment-prewrap">{q.prompt}</p>{q.choices.map((c) => <p key={c.id} className={correctIds(q).includes(c.id) ? 'assessment-correct' : ''}>{correctIds(q).includes(c.id) ? '✓ ' : '○ '}{c.text}</p>)}</article>)}{info.hint && <p>Gợi ý: {info.hint}</p>}</div>}</> : <AssessmentRunner key={info.id} path={detailPath} info={info} onTestActive={onTestActive} onRefresh={() => setRevision((v) => v+1)} />}
    </>}
    {(creating || editing) && <AssessmentEditor key={editing ? selected.id : 'new'} value={editing ? info : null} onClose={() => { onCreatingChange(false); setEditing(false) }} onSave={async (values) => { const data = await assessmentWrite(editing ? detailPath : path, editing ? 'PATCH' : 'POST', values); await onRefresh(); onSelect(data.id); setLoaded(data); onCreatingChange(false); setEditing(false) }} />}
    {removing && <VideoDialog title="Gỡ bài tập?" pending={busy} onClose={() => setRemoving(false)}><p>Học viên sẽ không còn mở được bài này. Lịch sử bài làm được giữ nội bộ.</p>{error && <p className="error-banner" role="alert">{error}</p>}<div className="video-dialog-actions"><button className="outline-button" type="button" disabled={busy} onClick={() => setRemoving(false)}>Hủy</button><button className="solid-button" type="button" disabled={busy} onClick={async () => { setBusy(true); try { await assessmentWrite(detailPath, 'DELETE'); await onRefresh(); onSelect(null); setLoaded(null); setRemoving(false) } catch (err) { setError(courseErrorMessage(err)) } finally { setBusy(false) } }}>Xác nhận gỡ</button></div></VideoDialog>}
  </section>
}
